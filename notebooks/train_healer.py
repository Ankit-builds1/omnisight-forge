"""QLoRA training of the Healer on Kaggle (one T4, internet on).

Needs `pip install bitsandbytes` and exactly one attached dataset made by `python -m forge.export`.
Writes zero-shot and fine-tuned answers for the held-out sites and the LoRA adapter (zipped)
to /kaggle/working. Grade the answer files locally with forge.scoring.
"""

# ruff: noqa: E402
import os

os.environ["PYTORCH_ALLOC_CONF"] = "expandable_segments:True"

import glob
import json
import random
import shutil
import time

import torch
import torch.nn.functional as F
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
from PIL import Image
from transformers import AutoProcessor, BitsAndBytesConfig, Qwen3VLForConditionalGeneration

MODEL = "Qwen/Qwen3-VL-4B-Instruct"
MAX_PIXELS = 640 * 640
MAX_TRAIN_TOKENS = 4000
MAX_NEW_TOKENS = 256
EPOCHS = 2
GRAD_ACCUM = 4
LR = 2e-4
OUT = "/kaggle/working"

used = torch.cuda.memory_allocated() / 1e9
print("GPU memory in use at start GB:", round(used, 2))
assert used < 0.5, "GPU not empty: restart the session before running this script"

random.seed(0)
torch.manual_seed(0)
found = glob.glob("/kaggle/input/**/train.jsonl", recursive=True)
assert len(found) == 1, f"expected exactly one dataset with train.jsonl, found: {found}"
DATA = os.path.dirname(found[0])
print("data folder:", DATA)


def read_jsonl(name):
    with open(os.path.join(DATA, name), encoding="utf-8") as f:
        return [json.loads(line) for line in f]


train_rows = read_jsonl("train.jsonl")
test_rows = read_jsonl("test.jsonl")
print("train", len(train_rows), "test", len(test_rows))

bnb = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_compute_dtype=torch.float16,
    bnb_4bit_use_double_quant=True,
)
processor = AutoProcessor.from_pretrained(MODEL)
model = Qwen3VLForConditionalGeneration.from_pretrained(
    MODEL,
    quantization_config=bnb,
    device_map={"": 0},
    dtype=torch.float16,
    attn_implementation="sdpa",
)


def load_image(path):
    img = Image.open(path).convert("RGB")
    scale = (MAX_PIXELS / (img.width * img.height)) ** 0.5
    if scale < 1:
        img = img.resize((int(img.width * scale), int(img.height * scale)))
    return img


def prompt_inputs(row):
    img = load_image(os.path.join(DATA, row["image"]))
    text = processor.apply_chat_template(
        row["messages"][:1], tokenize=False, add_generation_prompt=True
    )
    return processor(text=[text], images=[img], return_tensors="pt")


def encode(row):
    """Full conversation tokens, plus how many of them belong to the prompt."""
    img = load_image(os.path.join(DATA, row["image"]))
    full = processor.apply_chat_template(row["messages"], tokenize=False)
    batch = processor(text=[full], images=[img], return_tensors="pt")
    n_prompt = prompt_inputs(row)["input_ids"].shape[1]
    return batch, n_prompt


lengths = {row["sample_id"]: encode(row)[0]["input_ids"].shape[1] for row in train_rows}
longest = sorted(lengths.items(), key=lambda kv: kv[1], reverse=True)
print("longest training examples (tokens):", longest[:8], flush=True)
skipped = [sid for sid, n in longest if n > MAX_TRAIN_TOKENS]
print(f"skipped in training (> {MAX_TRAIN_TOKENS} tokens): {len(skipped)} {skipped}", flush=True)
train_rows = [row for row in train_rows if lengths[row["sample_id"]] <= MAX_TRAIN_TOKENS]
print("train rows used:", len(train_rows), flush=True)


def answer_loss(batch, n_prompt):
    """Loss on the answer tokens only; logits are computed only where they are needed."""
    ids = batch["input_ids"]
    n_answer = ids.shape[1] - n_prompt
    out = model(**batch, logits_to_keep=n_answer + 1)
    logits = out.logits[:, :-1].float()
    targets = ids[:, -n_answer:]
    return F.cross_entropy(logits.reshape(-1, logits.shape[-1]), targets.reshape(-1))


def predict(rows, path):
    model.eval()
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            inputs = prompt_inputs(row).to(model.device)
            with torch.no_grad():
                out = model.generate(**inputs, max_new_tokens=MAX_NEW_TOKENS, do_sample=False)
            raw = processor.batch_decode(
                out[:, inputs["input_ids"].shape[1]:], skip_special_tokens=True
            )[0]
            f.write(json.dumps({"sample_id": row["sample_id"], "raw": raw}) + "\n")
            print(row["sample_id"], "|", raw.replace("\n", " ")[:150], flush=True)


print("=== zero-shot 4B on test ===", flush=True)
predict(test_rows, f"{OUT}/zeroshot_4b_test.jsonl")
torch.cuda.empty_cache()

model = prepare_model_for_kbit_training(
    model,
    use_gradient_checkpointing=True,
    gradient_checkpointing_kwargs={"use_reentrant": False},
)
model.config.use_cache = False
lora = LoraConfig(
    r=16,
    lora_alpha=32,
    lora_dropout=0.05,
    target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
    task_type="CAUSAL_LM",
)
model = get_peft_model(model, lora)
model.print_trainable_parameters()
optimizer = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=LR)

print("=== training ===", flush=True)
start = time.time()
model.train()
for epoch in range(EPOCHS):
    order = train_rows[:]
    random.shuffle(order)
    total = 0.0
    for i, row in enumerate(order, 1):
        batch, n_prompt = encode(row)
        batch = batch.to(model.device)
        loss = answer_loss(batch, n_prompt)
        (loss / GRAD_ACCUM).backward()
        total += loss.item()
        print(f"  {epoch + 1}.{i:02d} {row['sample_id']:30s} "
              f"tokens={batch['input_ids'].shape[1]} loss={loss.item():.4f} "
              f"peak={torch.cuda.max_memory_allocated() / 1e9:.1f}GB", flush=True)
        if epoch == 0 and i == 1:
            trainable = [(n, p) for n, p in model.named_parameters() if p.requires_grad]
            missing = [n for n, p in trainable if p.grad is None]
            print("LoRA params without grad:", len(missing), flush=True)
            assert not missing, missing[:5]
        if i % GRAD_ACCUM == 0 or i == len(order):
            optimizer.step()
            optimizer.zero_grad()
    print(f"epoch {epoch + 1}: mean loss {total / len(order):.4f} "
          f"({(time.time() - start) / 60:.1f} min)", flush=True)

model.save_pretrained(f"{OUT}/adapter")
model.config.use_cache = True
print("=== fine-tuned 4B on test ===", flush=True)
predict(test_rows, f"{OUT}/finetuned_4b_test.jsonl")
print("peak GPU memory GB:", round(torch.cuda.max_memory_allocated() / 1e9, 2))
print(shutil.make_archive(f"{OUT}/adapter", "zip", f"{OUT}/adapter"))
print(sorted(os.listdir(OUT)))