import os
import re
import json
import random
from pathlib import Path

from flask import Flask, request, jsonify, Response, render_template
from openai import OpenAI

app = Flask(__name__)

# ============================================================
# НАСТРОЙКИ
# ============================================================

MODEL = os.getenv("OPENAI_MODEL", "gpt-6-luna")
BASE_URL = os.getenv("OPENAI_BASE_URL") or None
API_KEY = os.getenv("OPENAI_API_KEY")

if not API_KEY and BASE_URL:
    API_KEY = "ollama"  # для локальной Ollama

if not API_KEY:
    raise SystemExit(
        "Не задан OPENAI_API_KEY.\n"
        "Задайте переменную окружения OPENAI_API_KEY (или используйте OPENAI_BASE_URL для Ollama)."
    )

if BASE_URL:
    client = OpenAI(api_key=API_KEY, base_url=BASE_URL)
else:
    client = OpenAI(api_key=API_KEY)

SAVES_DIR = Path("saves")
SAVES_DIR.mkdir(exist_ok=True)


# ============================================================
# СИСТЕМНЫЙ ПРОМПТ — «живой мир»
# ============================================================

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
• Ощущения через 2–3 органа чувств в каждой сцене (что видно, слышно, чем пахнет), но без перегруза.
• Не пересказывай, что игрок только что сделал. Показывай РЕЗУЛЬТАТ.

════════ ЗАПРЕЩЁННЫЕ ФРАЗЫ И ПРИЁМЫ ════════
Никогда не пиши:
× «Вы стоите перед выбором»
× «Что вы будете делать?»
× «Ваше приключение начинается»
× «Избранный», «судьба зовёт», «древнее пророчество» (если жанр не про это)
× «Внезапно» более одного раза за сцену
× Мета-комментарии о механике в тексте («бросьте инициативу» пиши отдельной строкой в конце)
× Описания чужих мыслей за игрока
× Повторение имён NPC в каждом предложении — хватит одного-двух раз за ответ

════════ ЖИВОЙ МИР ════════
За кулисами веди 2–3 противоборствующие силы (фракции, личности, угрозы). У каждой:
• цель (чего хочет)
• метод (как действует)
• часы от 1 до 6 (прогресс цели)

ПРАВИЛА ЧАСОВ:
• Часы тикают от действий игрока И от времени (каждая крупная сцена +1 к одной из сил).
• Когда часы доходят до 6 — цель силы сбывается: в мире что-то непоправимо меняется.
• Не раскрывай часы игроку напрямую. Мир проявляет их косвенно: слухи, следы, чужие трупы, цены на рынке, погода.
• Даже когда игрок отдыхает или бездействует — что-то в мире происходит.

════════ NPC ════════
У каждого значимого NPC есть:
• Имя, роль
• Одна яркая деталь внешности или привычки (шрам, тик, запах, тембр)
• Цель (чего хочет от игрока или от жизни)
• Тайна (что скрывает)
• Манера речи (грубая / певучая / лаконичная)

NPC:
• Отвечают в своей манере, а не «вежливо-нейтрально».
• Помнят, что игрок им сделал (помог, обманул, оскорбил).
• Могут лгать, если им выгодно.
• Не выкладывают всю информацию сразу — торгуются, намекают, увиливают.
• Меняют отношение к игроку по поступкам, а не по «сюжету».

════════ КАНОН СЕССИИ ════════
Запоминай и соблюдай:
• Имя, вид, класс, внешность персонажа игрока
• Установленный жанр и тон (готик-хоррор ≠ героика ≠ LitRPG)
• Все имена, места, предметы, договорённости, долги
• Уровень магии/технологий в этом мире (не вводи лазеры в фэнтези)

Если игрок противоречит канону — мягко поправь через мир, а не через мета-замечание.
Если забыл факт — верни его из истории, не выдумывай новый.

════════ УМЕСТНОСТЬ И РАМКИ ════════
• Не вводи новые силы, фракции и угрозы без причины, заложенной в сцене.
• Не переключай жанр на ходу (был хоррор — не превращай в комедию, если игрок сам не сменил тон).
• Масштаб событий соответствует масштабу действий игрока: не спасай мир из-за похода в таверну.
• Случайные события (d6 на удачу) — не чаще одного раза на 3–4 сцены.
• Если игрок пытается сломать игру («я нахожу у себя во рту ключ от всех дверей») — вежливо откажи через мир: «Ты шаришь языком по нёбу — только привкус крови и пыли».

════════ СТРУКТУРА ОТВЕТА ════════
Каждый ответ мастера строится по плану (без явных заголовков в тексте):
1. НЕМЕДЛЕННЫЙ РЕЗУЛЬТАТ — что произошло от действия игрока.
2. РЕАКЦИЯ МИРА — что изменилось вокруг, звуки, NPC, атмосфера.
3. ГОЛОС NPC — реплика, действие, взгляд (если рядом кто-то есть).
4. ВЫЗОВ — новая ситуация, вопрос или угроза, требующая ответа.

Ответ ВСЕГДА заканчивается на вызове. Не обрывай сцену «ничем».

════════ ПРОВЕРКИ И БРОСКИ ════════
• Если исход действия неочевиден — проси бросок: «Сделайте бросок 1d20+Мод (Сложность 15)». Не выдумывай результат броска.
• Результат броска (тебе присылают как [[БРОСОК]]):
  – 1 — критический провал: не только неудача, но и осложнение.
  – 2–9 — провал с ценой: почти получилось, но что-то пошло не так.
  – 10–14 — успех с осложнением: получилось, но появилась новая проблема.
  – 15–19 — чистый успех.
  – 20 — критический успех: сделай больше, чем ожидал игрок.
• Не проси броски на тривиальные действия (открыть незапертую дверь, взять предмет с полки).

════════ LitRPG-МЕХАНИКИ ════════
• XP давай за: решение проблем, победы, открытия, важные социальные ходы. Не за «поговорил со всеми».
• Уровень повышается, когда XP достигает xp_next. При повышении: +2 к max_hp, +1 к одной характеристике по выбору игрока, +1 новая способность (спроси, какую хочет).
• Инвентарь: предметы имеют вес/объём, если это важно для сцены. Не превращай в бухгалтерию.
• HP снижай за реальные раны, а не за «плохое настроение». При HP=0 — персонаж без сознания, не мёртв (если игрок не решит иначе).
• Условия («отравлен», «истощён», «вдохновлён») добавляй только когда они реально влияют на броски.

════════ ЯЗЫК ════════
Отвечай на русском. Естественно, без канцелярита. Мат и жёсткость — только если жанр требует (например, Dark Sun, Равенлофт), и умеренно.

════════ СТАРТ ════════
Первый ответ — только после того, как игрок опишет персонажа, мир, тон и стартовую ситуацию (или выберет готовый мир). Не начинай сам.
"""


# ============================================================
# ЭКСТРАКТОР ЛИСТА ПЕРСОНАЖА
# ============================================================

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
    "stats": {"str": 10, "dex": 10, "con": 10, "int": 10, "wis": 10, "cha": 10},
    "inventory": [], "quests": [], "conditions": []
}


# ============================================================
# УТИЛИТЫ
# ============================================================

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
    """Достаём JSON из ответа модели, даже если она обернула в ```json ... ```."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("Нет JSON в ответе")
    return json.loads(text[start:end + 1])


def extract_state(messages, current_state):
    """Второй, быстрый вызов модели — только для обновления листа персонажа."""
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
        if not isinstance(merged.get("inventory"), list):
            merged["inventory"] = []
        if not isinstance(merged.get("quests"), list):
            merged["quests"] = []
        if not isinstance(merged.get("conditions"), list):
            merged["conditions"] = []
        return merged
    except Exception:
        return current_state


# ============================================================
# МАРШРУТЫ
# ============================================================

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
                model=MODEL,
                messages=messages,
                temperature=0.9,   # чуть выше для «живости» прозы
                stream=True,
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
    # Совместимость со старыми сохранениями (массив сообщений)
    if isinstance(data, list):
        data = {"messages": data, "state": DEFAULT_STATE}
    return jsonify(data)


# ============================================================
# ЗАПУСК
# ============================================================

if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
