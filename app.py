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
• Конкретика важнее эпитетов. Не «мрачный лес», а «сосны стоят так плотно, что снег не падает на землю».
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

════════ ЖИВОЙ МИР ════════
За кулисами веди 2–3 противоборствующие силы. У каждой:
• цель, метод, часы от 1 до 6 (прогресс цели)

ПРАВИЛА ЧАСОВ:
• Часы тикают от действий игрока И от времени (каждая крупная сцена +1 к одной из сил).
• Когда часы доходят до 6 — цель силы сбывается: в мире что-то непоправимо меняется.
• Не раскрывай часы игроку напрямую. Мир проявляет их косвенно.
• Даже когда игрок отдыхает — что-то в мире происходит.

════════ СОЗДАНИЕ ПЕРСОНАЖА (раса и класс) ════════
Когда игрок впервые описывает персонажа (или выбирает готовый мир), ты ОБЯЗАН:

1. Определить РАСУ и КЛАСС персонажа из описания. Если игрок не указал — предложи 2–3 варианта и спроси, что выбирает. Не начинай игру, пока не определены.
2. Выставить БАЗОВЫЕ характеристики (до 10–16) в зависимости от класса:
   • Воин/Варвар/Паладин: Сила 15, Телосложение 14, остальные 10–12
   • Плут/Следопыт/Монах: Ловкость 15, остальные 10–12
   • Маг: Интеллект 15, Ловкость 12, остальные 10–11
   • Жрец/Друид: Мудрость 15, Телосложение 12, остальные 10–11
   • Бард/Колдун/Чародей: Харизма 15, Ловкость 12, остальные 10–11
3. Применить РАСОВЫЕ БОНУСЫ к базовым характеристикам:
   • Человек: +1 ко всем
   • Эльф/Полуэльф: +2 Ловкость, +1 Интеллект (полуэльф — на выбор Ловкость или Харизма)
   • Дворф: +2 Телосложение, +1 Сила
   • Полурослик: +2 Ловкость, +1 Харизма
   • Гном: +2 Интеллект, +1 Телосложение
   • Полуорк/Орк: +2 Сила, +1 Телосложение
   • Тифлинг: +2 Харизма, +1 Интеллект
   • Драконорождённый: +2 Сила, +1 Харизма
   • Гоблин/Кобольд: +2 Ловкость, +1 к Интеллекту/Телосложению
4. Объявить игроку итог: «Кейр, эльф-плут. Ловкость 17 (+2 от эльфа), Интеллект 13, Харизма 10, Телосложение 12, Мудрость 10, Сила 8. HP 10/10, золото 0».

НЕ пересчитывай характеристики после создания без причины (повышение уровня, проклятие, магический предмет). Если игрок сам хочет поменять расу/класс — пересчитай честно.

════════ МОДИФИКАТОР СЛОЖНОСТИ (DC) — ДИНАМИЧЕСКИЙ ════════
Перед КАЖДЫМ броском ты обязан явно объявить DC и причины, почему он такой.

БАЗОВЫЙ DC по сложности задачи:
• 5 — очень легко (заметить слона в комнате)
• 10 — легко (перелезть невысокий забор)
• 15 — средне (взломать простой замок, убедить стража)
• 20 — сложно (взломать сейф, обмануть опытного мага)
• 25 — очень сложно (пробраться в хорошо охраняемую крепость)
• 30 — почти невозможно (украсть у божества)

МОДИФИКАТОРЫ К DC (прибавляй/убавляй от базового):
Ситуация ухудшает — DC растёт:
+3 темнота (ночь, подвал); +5 полная темнота (слепота)
+2 ранение (HP < 50%); +3 критическое ранение (HP < 25%)
+2 отравлен / болезнь / истощён
+2 испуган / паника
+2 враждебный NPC (для социальных проверок)
+1..+2 пересечённая местность (грязь, камни, крутой склон)
+1..+2 шум / помехи / плохая видимость (туман, дым)
+2 спешка (действие за раунд, ограничение по времени)
+1..+2 незнакомая территория

Ситуация улучшает — DC падает:
-2 союзник помогает (не больше -2 за раз)
-2..-3 тщательная подготовка (осмотрел, изучил, приготовился)
-2 преимущество от тактики, магии, окружения
-1..-2 знакомое место / знакомый NPC

Как объявлять бросок:
«Сделайте бросок 1d20+<Модификатор> (Сложность <Итог>: база <X> + <причины>)».
Пример: «Сделайте бросок 1d20+3 (Ловкость) (Сложность 17: база 15 + 2 за темноту)».
Модификатор к броску — из характеристик персонажа (Ловкость 14 → +2).

ПРАВИЛА:
• Никогда не назначай броски на тривиальные действия (открыть незапертую дверь, взять предмет).
• Если DC < 10 — игрок автоматически успешен, бросок не нужен. Просто опиши результат.
• Если DC > 25 и игрок явно не подготовлен — сначала предупреди в тексте: «Задача почти невозможна: без света, раненый, ты вряд ли справишься».
• Модификатор сложности (итоговый − базовый) сохраняется в листе как «dc_modifier». Когда обстоятельства меняются — пересчитывай.

Результаты броска ([[БРОСОК]]):
– 1 — критический провал + осложнение
– 2–9 — провал с ценой
– 10–14 — успех с осложнением
– 15–19 — чистый успех
– 20 — критический успех, больше ожидаемого
Сравнивай результат с DC, который ты объявил ранее.

════════ СТРУКТУРА ОТВЕТА ════════
1. НЕМЕДЛЕННЫЙ РЕЗУЛЬТАТ — что произошло.
2. РЕАКЦИЯ МИРА — что изменилось вокруг.
3. ГОЛОС NPC — реплика, действие (если рядом кто-то есть).
4. ВЫЗОВ — новая ситуация, вопрос, угроза или требование броска.

Ответ ВСЕГДА заканчивается на вызове.

════════ NPC ════════
У каждого значимого NPC есть: имя, роль, яркая деталь, цель, тайна, манера речи.
NPC отвечают в своей манере, помнят поступки игрока, могут лгать, не выкладывают всё сразу, меняют отношение по поступкам.

════════ КАНОН СЕССИИ ════════
Запоминай и соблюдай: имя/расу/класс персонажа, характеристики, жанр, все имена, места, предметы, договорённости. Не вводи лазеры в фэнтези, не превращай хоррор в комедию.

════════ УМЕСТНОСТЬ И РАМКИ ════════
• Не вводи новые силы/фракции без причины, заложенной в сцене.
• Не переключай жанр на ходу.
• Масштаб событий соответствует масштабу действий.
• Случайные события (d6) — не чаще одного раза на 3–4 сцены.
• Если игрок ломает игру — вежливо откажи через мир.

════════ LitRPG-МЕХАНИКИ ════════
• XP за решение проблем, победы, открытия, важные социальные ходы.
• Уровень растёт при XP ≥ xp_next: +2 max_hp, +1 характеристика, +1 способность.
• Инвентарь — без бухгалтерии.
• HP снижай за реальные раны. HP=0 — без сознания, не мёртв.
• Условия добавляй только когда реально влияют.

════════ ЯЗЫК ════════
Русский, естественный, без канцелярита. Жёсткость — по жанру.

════════ СТАРТ ════════
Первый ответ — только после описания персонажа/мира или выбора готового мира. Сначала раса и класс, потом сцена.
"""


STATE_EXTRACT_PROMPT = """
Ты — модуль отслеживания состояния персонажа в RPG. На основе диалога обнови состояние.

Верни СТРОГО валидный JSON без markdown и комментариев:
{
  "name": "имя или Пустой",
  "race": "Человек",
  "class": "Воин",
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
  "faction_clocks": [],
  "dc_modifier": 0,
  "dc_modifier_reasons": []
}

ПРАВИЛА ДЛЯ ОСНОВНЫХ ПОЛЕЙ:
- Не выдумывай события, которых не было.
- Если значение неизвестно — сохрани из текущего состояния.
- XP не убывает. HP не превышает max_hp.
- Инвентарь/квесты — массивы коротких строк, без дублей.

ПРАВИЛА ДЛЯ RACE И CLASS:
- Если в диалоге названа раса/класс — сохрани. Если не названа — оставь как было.
- Не меняй без причины (смена расы/класса — только если это событие в игре).

ПРАВИЛА ДЛЯ STATS:
- Если раса или класс ТОЛЬКО ЧТО появились, а характеристики ещё дефолтные (10) — выставь:
  • Воин/Варвар/Паладин: Сила 15, Телосложение 14, остальные 10
  • Плут/Следопыт/Монах: Ловкость 15, остальные 10
  • Маг: Интеллект 15, Ловкость 12, остальные 10
  • Жрец/Друид: Мудрость 15, Телосложение 12, остальные 10
  • Бард/Колдун/Чародей: Харизма 15, Ловкость 12, остальные 10
- Затем примени расовые бонусы:
  • Человек: +1 ко всем
  • Эльф: +2 Ловкость, +1 Интеллект
  • Полуэльф: +2 Ловкость, +1 Харизма
  • Дворф: +2 Телосложение, +1 Сила
  • Полурослик: +2 Ловкость, +1 Харизма
  • Гном: +2 Интеллект, +1 Телосложение
  • Полуорк: +2 Сила, +1 Телосложение
  • Тифлинг: +2 Харизма, +1 Интеллект
  • Драконорождённый: +2 Сила, +1 Харизма
  • Гоблин/Кобольд: +2 Ловкость, +1 Телосложение
- Если характеристики уже не дефолтные (были раньше выставлены) — НЕ пересчитывай заново, только обновляй при повышении уровня.

ПРАВИЛА ДЛЯ DC_MODIFIER:
- dc_modifier — суммарный модификатор сложности от ТЕКУЩЕЙ ситуации:
  • Темнота/слепота: +3..+5
  • Ранение (HP < 50%): +2; критическое (HP < 25%): +3
  • Отравлен/болезнь/истощён: +2
  • Испуг/паника: +2
  • Пересечённая местность, шум, туман: +1..+2
  • Союзник помогает: -2
  • Подготовка/тактика: -2..-3
- dc_modifier_reasons — массив коротких причин: ["темнота +3", "ранен +2", "союзник −2"].
- Складывай причины алгебраически: например, темнота +3 и союзник −2 → итог +1.
- Если обстоятельства изменились (стало светло, рана зажила) — пересчитай.
- Если сейчас «нейтральная» ситуация — dc_modifier: 0, reasons: [].

ПРАВИЛА ДЛЯ RELATIONSHIPS:
Массив объектов: {"name":"Торвин","attitude":"насторожен","note":"помог один раз"}
- attitude: «враждебен» / «насторожен» / «нейтрален» / «дружелюбен» / «предан»
- Только значимые NPC, максимум 6–8 записей.

ПРАВИЛА ДЛЯ FACTION_CLOCKS:
Массив объектов: {"name":"Культ Змея","progress":3,"max":6,"goal":"пробудить древнего"}
- 2–3 силы. progress 1..max. Когда progress=max, цель сбывается, замени новой силой.
"""


SUMMARY_PROMPT = """
Ты — архивариус ролевой игры. Сожми старый фрагмент диалога в краткое резюме для продолжения.

СОХРАНИ:
- Ключевые события (что произошло, к чему привело)
- Имена NPC и отношение к игроку
- Принятые решения и их последствия
- Открытые вопросы, цели, долги
- Установленные факты мира (места, предметы, правила)
- Расу, класс и характеристики персонажа

НЕ ВКЛЮЧАЙ:
- Дословные реплики
- Эмоциональные описания и атмосферу
- Повторения

Формат: 1 плотный абзац, 3–6 предложений. Только суть, как заметка в дневнике.
"""

DICE_RE = re.compile(r"^\s*(\d*)d(\d+)([+-]\d+)?\s*$", re.IGNORECASE)

DEFAULT_STATE = {
    "name": "Пустой",
    "race": "",
    "class": "",
    "level": 1, "xp": 0, "xp_next": 100,
    "hp": 10, "max_hp": 10, "gold": 0,
    "stats": {"str": 10, "dex": 10, "con": 10, "int": 10, "wis": 10, "cha": 10},
    "inventory": [], "quests": [], "conditions": [],
    "relationships": [], "faction_clocks": [],
    "dc_modifier": 0, "dc_modifier_reasons": []
}


MAX_MESSAGES_BEFORE_SUMMARY = 25
KEEP_RECENT = 8


def summarize_old_messages(messages):
    if len(messages) <= MAX_MESSAGES_BEFORE_SUMMARY:
        return messages
    system = messages[0]
    body = messages[1:]
    if len(body) <= KEEP_RECENT * 2:
        return messages
    for m in messages:
        if m.get("role") == "system" and m.get("content", "").startswith("[РЕЗЮМЕ"):
            return messages
    to_summarize = body[:-KEEP_RECENT]
    recent = body[-KEEP_RECENT:]
    dialogue = "\n".join(
        f"{m['role']}: {m['content']}"
        for m in to_summarize if m.get("content")
    )
    if not dialogue.strip():
        return messages
    try:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": SUMMARY_PROMPT},
                {"role": "user", "content": f"ДИАЛОГ:\n{dialogue}\n\nСожми в резюме."},
            ],
            temperature=0.3,
        )
        summary = (resp.choices[0].message.content or "").strip()
        if not summary:
            return messages
        return [system, {"role": "system", "content": f"[РЕЗЮМЕ ПРОШЛОГО]\n{summary}"}] + recent
    except Exception:
        return messages


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
        merged["dc_modifier"] = int(merged.get("dc_modifier", 0) or 0)
        if not isinstance(merged.get("race"), str):
            merged["race"] = ""
        if not isinstance(merged.get("class"), str):
            merged["class"] = ""
        for f in ("inventory", "quests", "conditions", "relationships",
                  "faction_clocks", "dc_modifier_reasons"):
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

    messages = summarize_old_messages(messages)

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
