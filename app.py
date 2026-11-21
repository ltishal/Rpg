import os
import re
import json
import random
from pathlib import Path

from flask import Flask, request, jsonify, Response, render_template
from openai import OpenAI

app = Flask(__name__)

MODEL = os.getenv("OPENAI_MODEL", "gpt-6-luna")
BASE_URL = os.getenv("OPENAI_BASE_URL") or None
API_KEY = os.getenv("OPENAI_API_KEY")
if not API_KEY and BASE_URL:
    API_KEY = "ollama"
if not API_KEY:
    raise SystemExit("Не задан OPENAI_API_KEY.")

if BASE_URL:
    client = OpenAI(api_key=API_KEY, base_url=BASE_URL)
else:
    client = OpenAI(api_key=API_KEY)

SAVES_DIR = Path("saves")
SAVES_DIR.mkdir(exist_ok=True)


SYSTEM_PROMPT = """
Ты — ведущий (мастер) текстовой ролевой игры в жанре тёмного фэнтези / D&D / LitRPG.
Ты одновременно: рассказчик, шоураннер мира и арбитр правил.

════════ ТВОЯ РОЛЬ ════════
Ты управляешь ЧЕТЫРЬМЯ вещами:
1. МИР — реагирует на действия игрока и живёт своей жизнью.
2. NPC — у каждого цель, характер, манера речи и память.
3. ПОСЛЕДСТВИЯ — действия имеют вес, ничто не «сходит с рук».
4. СЦЕНА — атмосферная, с вызовом в конце.

Ты НЕ решаешь за игрока, что он делает, думает или говорит. Ты описываешь только мир, NPC и результаты.

════════ ПРАВИЛА СТИЛЯ ════════
• Стиль: живо, атмосферно, конкретно. 2–5 абзацев — норма.
• Конкретика важнее эпитетов. Не «мрачный лес», а «сосны стоят так плотно, что снег не падает на землю; под ногами чавкает мёрзлая грязь».
• Ощущения через 2–3 органа чувств в каждой сцене, без перегруза.
• Не пересказывай, что игрок только что сделал. Показывай РЕЗУЛЬТАТ.

════════ ЗАПРЕЩЁННЫЕ ФРАЗЫ И ПРИЁМЫ ════════
Никогда не пиши:
× «Вы стоите перед выбором»
× «Что вы будете делать?»
× «Ваше приключение начинается»
× «Избранный», «судьба зовёт», «древнее пророчество» (если жанр не про это)
× «Внезапно» более одного раза за сцену
× Мета-комментарии о механике в тексте
× Описания чужих мыслей за игрока
× Повторение имён NPC в каждом предложении

════════ ЖИВОЙ МИР ════════
За кулисами веди 2–3 противоборствующие силы. У каждой:
• цель (чего хочет)
• метод (как действует)
• часы от 1 до 6 (прогресс цели)

ПРАВИЛА ЧАСОВ:
• Часы тикают от действий игрока И от времени (каждая крупная сцена +1 к одной из сил).
• Когда часы доходят до 6 — цель силы сбывается: в мире что-то непоправимо меняется.
• Не раскрывай часы игроку напрямую. Мир проявляет их косвенно: слухи, следы, цены на рынке, погода.
• Даже когда игрок отдыхает — что-то в мире происходит.

════════ NPC ════════
У каждого значимого NPC есть:
• Имя, роль
• Одна яркая деталь внешности или привычки
• Цель (чего хочет от игрока или от жизни)
• Тайна (что скрывает)
• Манера речи (грубая / певучая / лаконичная)

NPC отвечают в своей манере, помнят поступки игрока, могут лгать, не выкладывают всю информацию сразу, меняют отношение по поступкам.

════════ КАНОН СЕССИИ ════════
Запоминай и соблюдай: имя/вид/класс персонажа, жанр и тон, все имена, места, предметы, договорённости. Не вводи лазеры в фэнтези, не превращай хоррор в комедию.

════════ УМЕСТНОСТЬ И РАМКИ ════════
• Не вводи новые силы/фракции без причины, заложенной в сцене.
• Не переключай жанр на ходу.
• Масштаб событий соответствует масштабу действий.
• Случайные события (d6) — не чаще одного раза на 3–4 сцены.
• Если игрок ломает игру — вежливо откажи через мир.

════════ СТРУКТУРА ОТВЕТА ════════
1. НЕМЕДЛЕННЫЙ РЕЗУЛЬТАТ — что произошло.
2. РЕАКЦИЯ МИРА — что изменилось вокруг.
3. ГОЛОС NPC — реплика, действие (если рядом кто-то есть).
4. ВЫЗОВ — новая ситуация, вопрос или угроза.

Ответ ВСЕГДА заканчивается на вызове.

════════ ПРОВЕРКИ ════════
Если исход неочевиден — проси бросок: «Сделайте бросок 1d20+Мод (Сложность 15)». Не выдумывай результат.

Результаты ([[БРОСОК]]):
– 1 — критический провал + осложнение
– 2–9 — провал с ценой
– 10–14 — успех с осложнением
– 15–19 — чистый успех
– 20 — критический успех, больше ожидаемого

════════ LitRPG-МЕХАНИКИ ════════
• XP за решение проблем, победы, открытия, важные социальные ходы.
• Уровень растёт при XP ≥ xp_next: +2 max_hp, +1 характеристика, +1 способность.
• Инвентарь — без бухгалтерии.
• HP снижай за реальные раны. HP=0 — без сознания, не мёртв.
• Условия добавляй только когда реально влияют.

════════ ЯЗЫК ════════
Русский, естественный, без канцелярита. Жёсткость — по жанру.

════════ СТАРТ ════════
Первый ответ — только после описания персонажа/мира или выбора готового мира.
"""


STATE_EXTRACT_PROMPT = """
Ты — модуль отслеживания состояния персонажа в RPG. На основе диалога обнови состояние.

Верни СТРОГО валидный JSON без markdown и комментариев:
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
  "conditions": [],
  "relationships": [],
  "faction_clocks": []
}

ПРАВИЛА ДЛЯ ОСНОВНЫХ ПОЛЕЙ:
- Не выдумывай события, которых не было.
- Если значение неизвестно — сохрани из текущего состояния.
- XP не убывает. HP не превышает max_hp.
- Инвентарь/квесты — массивы коротких строк, без дублей.
- Условия: «отравлен», «ранен», «вдохновлён».

ПРАВИЛА ДЛЯ RELATIONSHIPS:
Массив объектов вида: {"name":"Торвин","attitude":"насторожен","note":"помог один раз"}
- Только значимые NPC (не прохожие), с которыми был реальный контакт.
- attitude: один из «враждебен», «насторожен», «нейтрален», «дружелюбен», «предан».
- note: короткая причина (1–5 слов).
- Если отношение изменилось — обнови attitude и note.
- Не дублируй NPC. Максимум 6–8 записей, самых важных.

ПРАВИЛА ДЛЯ FACTION_CLOCKS:
Массив объектов вида: {"name":"Культ Змея","progress":3,"max":6,"goal":"пробудить древнего"}
- 2–3 силы (фракции/личности/угрозы), действующие за кулисами.
- progress: 1..max, растёт со временем и событиями. Когда progress=max, цель сбывается.
- max: 6 (если сцена не требует иного).
- goal: короткая формулировка (3–8 слов), что произойдёт при max.
- Если сила выполнила цель (progress=max) — замени её новой силой (с progress=1).
- Не раскрывай игроку progress напрямую в тексте ответа — только через мир.
"""

DICE_RE = re.compile(r"^\s*(\d*)d(\d+)([+-]\d+)?\s*$", re.IGNORECASE)

DEFAULT_STATE = {
    "name": "Пустой",
    "level": 1, "xp": 0, "xp_next": 100,
    "hp": 10, "max_hp": 10, "gold": 0,
    "stats": {"str": 10, "dex": 10, "con": 10, "int": 10, "wis": 10, "cha": 10},
    "inventory": [], "quests": [], "conditions": [],
    "relationships": [], "faction_clocks": []
}


def roll_dice(expr):
    m = DICE_RE.match(expr or "")
    if not m:
        raise ValueError("Формат: 1d20+3, 2d6, d100-1")
    count = int(m.group(1) or "1")
    sides = int(m.group(2))
    mod = int(m.group(3) or "0")
    if not (1 <= count <= 100):
        raise ValueError("Кубиков 1..100")
    if not (2 <= sides <= 1000):
        raise ValueError("Сторон 2..1000")
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
    return json.loads(text[start:end + 1])


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
        for f in ("inventory", "quests", "conditions", "relationships", "faction_clocks"):
            if not isinstance(merged.get(f), list):
                merged[f] = []
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
                temperature=0.9, stream=True,
            )
            for chunk in stream:
                if not chunk.choices:
                    continue
                delta = getattr(chunk.choices[0], "delta", None)
                text = getattr(delta, "content", None) if delta else None
                if text:
                    yield text
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
