import os
import re
import json
import random
from pathlib import Path

from flask import Flask, request, jsonify, Response, render_template
from openai import OpenAI

app = Flask(__name__)

MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
BASE_URL = os.getenv("OPENAI_BASE_URL") or None
API_KEY = os.getenv("OPENAI_API_KEY")
if not API_KEY and BASE_URL:
    API_KEY = "ollama"
if not API_KEY:
    raise SystemExit("Не задан OPENAI_API_KEY. Запустите через setup_rpg.py")

client = OpenAI(api_key=API_KEY, base_url=BASE_URL) if BASE_URL else OpenAI(api_key=API_KEY)

SAVES_DIR = Path("saves")
SAVES_DIR.mkdir(exist_ok=True)

SYSTEM_PROMPT = """
Ты — ведущий текстовой ролевой игры в жанре тёмного фэнтези / D&D / LitRPG.
Ты управляешь миром, NPC, сюжетом, проверками, боями и последствиями.

ПРАВИЛА:
1. Никогда не решай за игрока, что он делает, думает или говорит.
2. Всегда заканчивай ответ новой ситуацией, вопросом или вызовом.
3. Помни факты, имена, локации, цели, травмы, долги и обещания.
4. Используй механики LitRPG: уровень, XP, характеристики, инвентарь, квесты, лут.
5. Если исход неочевиден — попроси бросок: «Сделайте бросок 1d20+Мод». Не выдумывай результат.
6. После броска опиши успех, провал или осложнение честно и драматургично.
7. Стиль: живо, атмосферно, 2-5 абзацев.
8. Не описывай действия игрока без его ввода.
9. Отвечай на русском.
"""

STATE_EXTRACT_PROMPT = """
Ты — модуль отслеживания состояния персонажа в RPG. На основе диалога обнови состояние.

Верни СТРОГО валидный JSON без markdown и комментариев, в точно таком формате:
{
  "name": "имя или Пустой",
  "level": 1,
  "xp": 0,
  "xp_next": 100,
  "hp": 10,
  "max_hp": 10,
  "gold": 0,
  "stats": {"str":10,"dex":10,"con":10,"int":10,"wis":10,"cha":10},
  "inventory": [],
  "quests": [],
  "conditions": []
}

ПРАВИЛА:
- Не выдумывай события, которых не было в диалоге.
- Если значение неизвестно — сохрани из текущего состояния.
- XP не может убывать. HP не может превышать max_hp.
- Инвентарь и квесты — массивы коротких строк. Не дублируй.
- Если персонаж получил предмет — добавь. Потратил/потерял — убери.
- Условия: «отравлен», «ранен», «вдохновлён» и т.п.
"""

DICE_RE = re.compile(r"^\s*(\d*)d(\d+)([+-]\d+)?\s*$", re.IGNORECASE)

DEFAULT_STATE = {
    "name": "Пустой",
    "level": 1, "xp": 0, "xp_next": 100,
    "hp": 10, "max_hp": 10, "gold": 0,
    "stats": {"str":10,"dex":10,"con":10,"int":10,"wis":10,"cha":10},
    "inventory": [], "quests": [], "conditions": []
}


def roll_dice(expr):
    m = DICE_RE.match(expr or "")
    if not m:
        raise ValueError("Формат: 1d20+3, 2d6, d100-1")
    count = int(m.group(1) or "1")
    sides = int(m.group(2))
    mod = int(m.group(3) or "0")
    if not (1 <= count <= 100): raise ValueError("Кубиков 1..100")
    if not (2 <= sides <= 1000): raise ValueError("Сторон 2..1000")
    rolls = [random.randint(1, sides) for _ in range(count)]
    return {"expr": expr, "rolls": rolls, "mod": mod, "total": sum(rolls) + mod}


def clean_json(text):
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("Нет JSON")
    return json.loads(text[start:end+1])


def extract_state(messages, current_state):
    recent = messages[-14:]
    dialogue = "\n".join(
        f"{m['role']}: {m['content']}" for m in recent if m.get("content")
    )
    prompt = (
        f"ТЕКУЩЕЕ СОСТОЯНИЕ:\n{json.dumps(current_state, ensure_ascii=False)}\n\n"
        f"ДИАЛОГ:\n{dialogue}\n\n"
        "Верни обновлённое состояние в формате JSON."
    )
    try:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": STATE_EXTRACT_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
        )
        raw = resp.choices[0].message.content or ""
        new_state = clean_json(raw)
        merged = dict(DEFAULT_STATE)
        merged.update({k: v for k, v in new_state.items() if v is not None})
        merged["hp"] = max(0, min(int(merged.get("hp", 0)), int(merged.get("max_hp", 1))))
        merged["level"] = max(1, int(merged.get("level", 1)))
        merged["xp"] = max(0, int(merged.get("xp", 0)))
        merged["gold"] = max(0, int(merged.get("gold", 0)))
        if not isinstance(merged.get("inventory"), list): merged["inventory"] = []
        if not isinstance(merged.get("quests"), list): merged["quests"] = []
        if not isinstance(merged.get("conditions"), list): merged["conditions"] = []
        return merged
    except Exception:
        return current_state


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/roll", methods=["POST"])
def api_roll():
    data = request.get_json(silent=True) or {}
    try:
        return jsonify(roll_dice(data.get("expr", "")))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/chat", methods=["POST"])
def api_chat():
    data = request.get_json(silent=True) or {}
    messages = data.get("messages") or []
    if not isinstance(messages, list) or not messages:
        return jsonify({"error": "empty messages"}), 400
    if messages[0].get("role") != "system":
        messages = [{"role": "system", "content": SYSTEM_PROMPT}] + messages

    def generate():
        try:
            stream = client.chat.completions.create(
                model=MODEL, messages=messages,
                temperature=0.85, stream=True,
            )
            for chunk in stream:
                if not chunk.choices: continue
                delta = getattr(chunk.choices[0], "delta", None)
                text = getattr(delta, "content", None) if delta else None
                if text: yield text
        except Exception as e:
            yield f"\n[Ошибка API: {e}]"

    return Response(generate(), mimetype="text/plain; charset=utf-8")


@app.route("/api/state", methods=["POST"])
def api_state():
    data = request.get_json(silent=True) or {}
    messages = data.get("messages") or []
    state = data.get("state") or DEFAULT_STATE
    if not isinstance(messages, list) or not messages:
        return jsonify(state)
    return jsonify(extract_state(messages, state))


@app.route("/api/saves")
def api_saves_list():
    return jsonify(sorted(p.stem for p in SAVES_DIR.glob("*.json")))


@app.route("/api/save", methods=["POST"])
def api_save():
    data = request.get_json(silent=True) or {}
    name = re.sub(r"[^a-zA-Z0-9_\-]", "", data.get("name") or "") or "default"
    payload = {
        "messages": data.get("messages") or [],
        "state": data.get("state") or DEFAULT_STATE,
    }
    (SAVES_DIR / f"{name}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return jsonify({"ok": True, "name": name})


@app.route("/api/load/<name>")
def api_load(name):
    name = re.sub(r"[^a-zA-Z0-9_\-]", "", name)
    path = SAVES_DIR / f"{name}.json"
    if not path.exists():
        return jsonify({"error": "not found"}), 404
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        data = {"messages": data, "state": DEFAULT_STATE}
    return jsonify(data)


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
