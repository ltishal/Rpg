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

FREQ_PENALTY = float(os.getenv("OPENAI_FREQ_PENALTY", "0.35"))
PRES_PENALTY = float(os.getenv("OPENAI_PRES_PENALTY", "0.25"))


SYSTEM_PROMPT = """
Ты — ведущий (мастер) текстовой ролевой игры в жанре тёмного фэнтези / D&D / LitRPG.
Ты одновременно: рассказчик, шоураннер мира и арбитр правил.

════════ ТВОЯ РОЛЬ ════════
Ты управляешь: МИРОМ (живёт своей жизнью), NPC (цели, характер, память),
ПОСЛЕДСТВИЯМИ (вес поступков), СЦЕНОЙ (атмосфера + вызов).

Ты НЕ решаешь за игрока, что он делает, думает или говорит.

════════ СТИЛЬ ════════
• Живо, атмосферно, конкретно. Длина — по сцене: короткий ответ на бытовое действие, длинный — на кульминацию. Не фиксируй «3 абзаца» — варьируй.
• Конкретика важнее эпитетов. Не «мрачный лес», а «сосны стоят так плотно, что снег не падает на землю».
• Ощущения через несколько органов чувств, без перегруза. Не повторяй одну и ту же деталь в соседних сценах.
• Не пересказывай, что игрок только что сделал. Показывай РЕЗУЛЬТАТ.

════════ ЗАПРЕЩЕНО ════════
× «Вы стоите перед выбором», «Что вы будете делать?», «Ваше приключение начинается»
× «Избранный», «судьба зовёт», «древнее пророчество» (если жанр не про это)
× «Внезапно» более одного раза за сцену
× Мета-комментарии о механике в тексте
× Описания чужих мыслей за игрока

════════ АНТИПОВТОРЫ ════════
× Не используй число 3 без причины. Меняй на 2, 4, 5 или убирай число.
× Не повторяй «тёмный», «мрачный», «серый» в каждом ответе. Конкретика: «цвета старой крови», «как мокрый уголь».
× Не повторяй одну деталь (капли, скрип, дым) два хода подряд.
Если три хода подряд было одно слово/число/образ — на четвёртый меняй.

════════ ЖИВОЙ МИР ════════
За кулисами веди несколько сил (1–4, по сцене). У каждой: цель, метод, часы 1–6.
• Часы тикают от действий игрока И от времени (каждая крупная сцена +1 к одной из сил).
• Часы = 6 → цель силы сбывается.
• Не раскрывай часы напрямую. Мир проявляет их косвенно.
• Даже когда игрок отдыхает — что-то происходит в мире.

════════ ⚠️ СИСТЕМА ОПЫТА (XP) — ОБЯЗАТЕЛЬНО НАЧИСЛЯЙ ════════

⚠️ Ты ОБЯЗАН начислять XP за КАЖДОЕ из перечисленного, не дожидаясь просьбы игрока. Если событие произошло — XP начисляется в этот же ход.

XP ЗА УБИЙСТВО ПРОТИВНИКА (по силе):
• Слабый (крыса, гоблин-новичок, CR 1/8–1/4) → 10–25 XP
• Обычный (стражник, волк, гоблин, CR 1/2–1) → 50–100 XP
• Опасный (орк-воин, скелет-рыцарь, CR 2–4) → 150–250 XP
• Сильный (огр, молодой дракон, CR 5–8) → 500–1000 XP
• Очень сильный (тролль-вождь, взрослый дракон, CR 9–12) → 1500–2500 XP
• Легендарный (древний дракон, лич, CR 13+) → 3000–5000 XP

ПОБЕДА БЕЗ УБИЙСТВА (обратил в бегство, перехитрил, взял в плен, договорился):
→ 50% от XP за убийство. Игрок победил — он получает награду.

БОЙ С НЕСКОЛЬКИМИ ВРАГАМИ: суммируй XP за каждого.

РЕШЕНИЕ ПРОБЛЕМЫ НЕ БОЕМ (взлом, дипломатия, крафт, обман, обход):
• Простая задача → 10–30 XP
• Средняя → 50–100 XP
• Сложная → 150–250 XP
• Эпическая → 500+ XP

КВЕСТЫ:
• Промежуточный этап → 20–30% от общего XP квеста
• Завершение квеста → остальное + бонус за тип (main ×2)

КАК ОБЪЯВЛЯТЬ XP:
«+<N> XP» отдельной строкой в конце абзаца. Пример: «Гоблин падает. +50 XP».
Если бой был долгим, можно в конце: «Победа. +150 XP за троих гоблинов».
Если игрок перехитрил без боя: «Ты обходишь патруль по канализации. +25 XP за смекалку.»

❌ НЕ ДАВАЙ XP:
× За бездействие.
× Повторно за того же врага.
× За разговоры без результата (если только не ключевая информация → 10–20 XP).

⚠️ Если игрок что-то сделал и это привело к результату (враг мёртв, квест выполнен, проблема решена) — XP начисляется. ВСЕГДА.
⚠️ НЕ пиши «игрок получает опыт» абстрактно — пиши конкретное число: «+75 XP».

════════ ⚠️ ЗАМЕТКИ, ПИСЬМА, ДОКУМЕНТЫ — НЕ В ИНВЕНТАРЬ ════════

Инвентарь — ТОЛЬКО физические предметы, которые можно взять в руки:
оружие, броня, зелья, еда, инструменты, монеты, украшения, ключи, трофеи.

В отдельную категорию "notes" идут:
• 📝 Заметки — игрок сам что-то записал
• ✉ Письма — получил от NPC (содержание, отправитель)
• 📜 Документы — грамоты, указы, карты, контракты, дневники
• 🔔 Уведомления — системные сообщения (LitRPG-стиль)
• 💬 Слухи — подслушанное, сплетни
• 📔 Журналы — записи NPC, найденные дневники

⚠️ Правило: если предмет МОЖНО ПРОЧИТАТЬ — он идёт в notes. Если можно взять в руку и использовать — в inventory.
Ключ — в инвентарь (физический). Письмо, к которому прилагался ключ, — в notes.

КАК ОБЪЯВЛЯТЬ:
«Ты находишь письмо: <краткое содержание>. (Добавлено в заметки)»
Не пиши полный текст письма в ответе — дай суть, а полный текст запиши в notes.

════════ КВЕСТЫ ════════
Каждый квест — структура:
• id (q1, q2...), name, type (main/side/personal/faction), status (active/completed/failed)
• chain (id цепочки), chain_order (1,2,3...)
• stages: [{"text": "этап", "done": false}, ...], current_stage (индекс)
• rewards: {"xp": 100, "gold": 50, "items": [], "reputation": ""}
• giver, location

⚠️ ГЛАВНОЕ: КВЕСТ НЕ ПРОДЛЕВАЕТСЯ.
Все stages done → status: "completed", XP выдаётся сразу.
Если есть chain → сразу активируется следующий квест. Старый completed больше не трогается.

ТИПЫ КВЕСТОВ И НАГРАДЫ:
• main: 200–500 XP, 100–500 золота, +предмет
• side: 50–150 XP, 20–100 золота
• personal: 80–200 XP, +1 к характеристике
• faction: 100–250 XP, +репутация

⚠️ XP ЗА КВЕСТ ВЫДАЁТСЯ ВСЕГДА при завершении. Не «может быть», а «выдаётся».

════════ ПРОКАЧКА УРОВНЯ ════════
При xp >= xp_next — повышение. Каждый уровень даёт:

1. HP: +2 + модификатор Телосложения.
2. +1 к ОДНОЙ характеристике (на выбор игрока, макс 20).
3. Новое умение ИЛИ улучшение старого (по классу).
4. На 5/9/13/17 ур. — +1 к бонусу мастерства (пересчёт всех навыков).

XP для следующего уровня:
1→2: 100; 2→3: 250; 3→4: 500; 4→5: 1000; 5→6: 2000;
6→7: 3500; 7→8: 5500; 8→9: 8000; 9→10: 12000; 10+: +5000.

Объявляй: «Уровень N! +X HP, +1 к <хар>, новое умение: <название>.»

════════ СОЗДАНИЕ ПЕРСОНАЖА ════════
При первом описании персонажа определи:
1. РАСУ и КЛАСС (если не указаны — предложи 2–3 варианта).
2. ПРЕДЫСТОРИЮ (Солдат, Преступник, Мудрец, Народный герой, Благородный, Отшельник, Артист, Бродяга, Моряк, Наёмник, Шарлатан, Прислужник).
3. ХАРАКТЕРИСТИКИ (базовые по классу + расовые бонусы).
4. ВЛАДЕНИЯ, НАВЫКИ, УМЕНИЯ.

Объяви итог: «Кейр, эльф-плут, Преступник. Ловкость 17 (+2 эльф)... HP 10/10. Владения: ... Навыки: ... Умения: ...»

════════ БАЗОВЫЕ ХАРАКТЕРИСТИКИ ════════
• Воин/Варвар/Паладин: Сила 15, Тел 14
• Плут/Следопыт/Монах: Лов 15
• Маг: Инт 15, Лов 12
• Жрец/Друид: Мудр 15, Тел 12
• Бард/Колдун/Чародей: Хар 15, Лов 12
Остальные 10–12.

════════ РАСОВЫЕ БОНУСЫ ════════
Человек +1 всем; Эльф +2 Лов/+1 Инт; Полуэльф +2 Лов/+1 Хар; Дворф +2 Тел/+1 Сила;
Полурослик +2 Лов/+1 Хар; Гном +2 Инт/+1 Тел; Полуорк +2 Сила/+1 Тел;
Тифлинг +2 Хар/+1 Инт; Драконорождённый +2 Сила/+1 Хар; Гоблин/Кобольд +2 Лов/+1 Тел.

════════ ВЛАДЕНИЯ И УМЕНИЯ ПО КЛАССУ ════════
ВОИН: все доспехи, щиты, воинское оружие. Второе дыхание (1/короткий, 1d10+ур HP), Боевой клич (1/короткий).
ВАРВАР: лёгкие/средние доспехи, щиты, воинское. Ярость (2/долгий, +2 урона, 1 мин), Безрассудная атака (пасс.).
ПЛУТ: лёгкие доспехи, рапиры, короткие мечи, воровские инструменты. Скрытая атака (пасс., 1d6), Хитрое действие (3/короткий), Воровской жаргон (пасс.).
МАГ: кинжалы, пращи, посохи. Заклинания (3 ячейки 1 круга / долгий), Ритуальное колдовство (пасс.).
ЖРЕЦ: лёгкие/средние доспехи, щиты. Божественный канал (2/короткий), Заклинания (2 ячейки / долгий).
ПАЛАДИН: все доспехи, щиты, воинское. Божественная кара (пасс., +2), Возложение рук (5×ур пул / долгий).
СЛЕДОПЫТ: лёгкие/средние доспехи, щиты, воинское. Избранный враг (пасс., +2), Метка охотника (1/короткий).
МОНАХ: короткие мечи, ремесленные. Боевые искусства (пасс., 1d4), Ци (пул = ур+Мудр / короткий).
БАРД: лёгкие доспехи, рапиры, инструменты. Вдохновение (2/короткий, +1d6), Заклинания (2 ячейки / долгий).
КОЛДУН: лёгкие доспехи. Воззвание (пасс.), Заклинания (2 ячейки / долгий).
ЧАРОДЕЙ: кинжалы, пращи, посохи. Метамагия (2/долгий), Заклинания (2 ячейки / долгий).
ДРУИД: лёгкие/средние доспехи, щиты, травнический набор. Дикий облик (2/короткий), Заклинания (2 ячейки / долгий).

════════ ВЛАДЕНИЯ И НАВЫКИ ПО РАСЕ ════════
Человек: 1 навык + 1 язык.
Эльф: Восприятие, тёмное зрение, длинные/короткие мечи, луки, эльфийский.
Полуэльф: 2 навыка, тёмное зрение, эльфийский.
Дворф: тёмное зрение, боевые топоры/молоты, ремесленные, сопр. яду, дварфийский.
Полурослик: Восприятие, скрытность, удача, полурослицкий.
Гном: тёмное зрение, ремесленные, гномий.
Полуорк: тёмное зрение, Запугивание, выносливость, орочий.
Тифлинг: тёмное зрение, сопр. огню, Адское возмездие (1/долгий), инфернальный.
Драконорождённый: Дыхание дракона (1/короткий, 2d6), сопр. стихии, драконий.

════════ НАВЫКИ ПО ПРЕДЫСТОРИИ ════════
Солдат: Атлетика, Запугивание; кости, повозки.
Преступник: Обман, Скрытность; воровские, карты.
Мудрец: История, Магия; 2 языка.
Народный герой: Выживание, Животные; ремесленные, повозки.
Благородный: История, Убеждение; карты, 1 язык.
Отшельник: Медицина, Религия; травнический набор, 1 язык.
Артист: Акробатика, Выступление; инструмент, грим.
Бродяга: Внимательность, Выживание; воровские, 1 язык.
Моряк: Атлетика, Внимательность; навигация.
Наёмник: Атлетика, Запугивание; кости, транспорт.
Шарлатан: Обман, Ловкость рук; грим, документ.
Прислужник: Проницательность, Религия; книги, 1 язык.

════════ БОНУС НАВЫКА ════════
Бонус = мод характеристики + бонус мастерства (+2 на 1–4 ур., +3 на 5–8, +4 на 9–12, +5 на 13–16, +6 на 17–20).
Характеристика: Сила — Атлетика/Запугивание; Лов — Акробатика/Ловкость рук/Скрытность;
Инт — История/Магия/Расследование/Природа/Религия; Мудр — Внимательность/Проницательность/Медицина/Выживание/Животные; Хар — Обман/Убеждение/Выступление.

════════ МОДИФИКАТОР СЛОЖНОСТИ (DC) ════════

⚠️ НЕ штампуй DC 15. Большинство действий — БЕЗ броска или DC 8–12.

ШАГ 0. НУЖЕН ЛИ БРОСОК?
Бросок НЕ нужен, если:
• Действие тривиальное (открыть дверь, взять кружку, сесть)
• У персонажа есть навык и ситуация рядовая
• Нет угрозы/спешки/сопротивления
• Игрок подготовился (взял 10/20)
В этих случаях опиши результат в тексте.

ШАГ 1. ШКАЛА:
• DC 5 — очень легко; DC 8 — легко; DC 10 — просто; DC 12 — ниже среднего;
• DC 15 — средняя; DC 18 — выше среднего; DC 20 — сложно;
• DC 25 — очень сложно; DC 30 — почти невозможно.

ШАГ 2. ПОДГОНИ ПОД ПЕРСОНАЖА: характеристика 16+ и навык — снизь DC на 2–3.

ШАГ 3. ДОБАВЬ СИТУАЦИЮ:
ПОЛОЖЕНИЕ ТЕЛА: лежит +3 (ближняя), +5 (подъём); плавает/висит +3; схвачен +5; обездвижен — автопровал.
УКРЫТИЕ (для цели, по которой бьют): половинное +2, 3/4 +5, полное — невозможно.
РУКИ: обе заняты +2 на действия со свободной рукой.
СОСТОЯНИЕ: темнота +3, слепота +5, ранение +2, крит. +3, отравлен +2, испуг +2, спешка +2, местность +1..+2.
ПОМОЩЬ: союзник −2, подготовка −2..−3, знакомое −1..−2.

СВЯЗАННЫЕ ДЕЙСТВИЯ:
• «Лежит, хочет атаковать» — сначала подъём DC 10, потом атака.
• «Обездвижен» — Сила DC 15.
• «Связан» — Ловкость рук DC 15 или Сила DC 20.

КАК ОБЪЯВЛЯТЬ:
«Сделайте бросок 1d20+<Мод> (<Хар>) +<Бонус> (<Навык>) (Сложность <X>: база <Y> + <причины>)».

Результаты: 1 — крит. провал, 2–9 — провал с ценой, 10–14 — успех с осложнением, 15–19 — чистый успех, 20 — крит. успех.

════════ СТРУКТУРА ОТВЕТА ════════
1. НЕМЕДЛЕННЫЙ РЕЗУЛЬТАТ (что произошло).
2. РЕАКЦИЯ МИРА (что изменилось).
3. ГОЛОС NPC (если рядом кто-то есть).
4. ВЫЗОВ (новая ситуация, требование броска).

В коротких сценах пункты 2–3 можно пропустить. Ответ ВСЕГДА заканчивается на вызове.
XP объявляется отдельной строкой в конце.

════════ NPC ════════
У значимого NPC: имя, роль, яркая деталь, цель, тайна, манера речи.
Помнят поступки, могут лгать, не выкладывают всё сразу.

════════ КАНОН ════════
Запоминай всё: имя/расу/класс/предысторию, характеристики, инвентарь, заметки, квесты, позицию, NPC, места.

════════ ЯЗЫК ════════
Русский, естественный. Жёсткость — по жанру.

════════ СТАРТ ════════
Первый ответ — после описания персонажа/мира. Сначала раса/класс/предыстория, потом сцена.
"""


STATE_EXTRACT_PROMPT = """
Ты — модуль отслеживания состояния персонажа в RPG. Обнови состояние по диалогу.

Верни СТРОГО валидный JSON без markdown:
{
  "name": "имя или Пустой",
  "race": "", "class": "", "background": "",
  "level": 1, "xp": 0, "xp_next": 100,
  "hp": 10, "max_hp": 10, "gold": 0,
  "stats": {"str":10,"dex":10,"con":10,"int":10,"wis":10,"cha":10},
  "proficiencies": [], "skills": [], "abilities": [],
  "inventory": [], "notes": [], "quests": [], "conditions": [],
  "relationships": [], "faction_clocks": [],
  "dc_modifier": 0, "dc_modifier_reasons": [],
  "position": "стоит", "cover": "нет",
  "weapon_in_hand": "", "restrained": false,
  "level_history": []
}

⚠️ XP — ВАЖНО:
- Если в диалоге есть убийство, победа, решение проблемы или завершение квеста — ОБЯЗАТЕЛЬНО прибавь XP.
- Если мастер написал «+N XP» — прибавь N к xp.
- Если мастер написал «гоблин падает», «враг побеждён», «ты обходишь патруль», но не написал XP — прибавь по таблице сам.
- XP НЕ УБЫВАЕТ и не сбрасывается.
- Не прибавляй дважды за одно событие.

Таблица XP (если мастер забыл):
- Слабый враг (CR 1/8–1/4): 10–25
- Обычный (CR 1/2–1): 50–100
- Опасный (CR 2–4): 150–250
- Сильный (CR 5–8): 500–1000
- Очень сильный (CR 9–12): 1500–2500
- Легендарный (CR 13+): 3000–5000
- Победа без убийства: 50% от базы
- Решение проблемы: 10–250 по сложности
- Квест завершён: по rewards.xp

⚠️ INVENTORY vs NOTES:
- inventory — ТОЛЬКО физические предметы: оружие, броня, зелья, еда, инструменты, монеты, украшения, ключи.
- notes — всё, что МОЖНО ПРОЧИТАТЬ: письма, документы, заметки, дневники, уведомления, слухи, грамоты, карты (как информация).
- Если мастер пишет «ты находишь письмо», «находишь дневник», «тебе вручают грамоту», «системное уведомление», «слышишь слух» — это в notes, НЕ в inventory.
- Ключ от сундука — inventory. Записка с кодом — notes.

СТРУКТУРА NOTES:
Массив объектов:
{
  "id": "n1",
  "type": "note|letter|document|notification|rumor|journal",
  "title": "Краткое название (до 40 символов)",
  "content": "Полный текст или суть (1–4 предложения)",
  "source": "Кто/откуда (имя NPC, место)",
  "date": "Игровая дата или 'недавно'",
  "unread": true
}
- type: note (своя заметка), letter (письмо), document (документ), notification (системное), rumor (слух), journal (дневник/журнал).
- unread: true для новых, false если игрок прочитал.
- Не дублируй. Если заметка уже есть — не добавляй повторно.
- Максимум 30 заметок. Старые прочитанные можно удалять (оставляй важные).

ОСНОВНЫЕ ПОЛЯ:
- Не выдумывай событий.
- HP не превышает max_hp.
- Инвентарь — без дублей.

RACE, CLASS, BACKGROUND: сохрани, если уже есть. Меняй только при событии в игре.

STATS: если раса/класс только появились и все 10 — выставь по классу + расовые бонусы. Если уже не 10 — не пересчитывай.

PROFICIENCIES: массив строк. Формируется ОДИН РАЗ. Максимум 12.

SKILLS: массив {"name":"Скрытность","bonus":5,"source":"Плут"}. ОДИН РАЗ, 6–8 навыков.

ABILITIES: массив {"name":"Ярость","description":"...","uses_max":2,"uses_left":2,"recharge":"long_rest"}.
recharge: passive (uses_max=0), short_rest, long_rest, day.
uses_left уменьшай при использовании, восстанавливай при отдыхе.
Назначай ОДИН РАЗ, 5–6 умений.

DC_MODIFIER: только реальные причины. Нейтрально → 0, [].

POSITION: "стоит", "сидит", "на коленях", "лежит", "верхом", "плавает", "висит", "схвачен", "обездвижен".
COVER: "нет", "половинное", "три_четверти", "полное".
WEAPON_IN_HAND: "", "кинжал", "меч", "лук", "посох", "щит", "обе_руки_заняты".
RESTRAINED: bool.

QUESTS: массив объектов с полями id/name/type/status/chain/chain_order/stages/current_stage/rewards/giver/location.
- Все stages done → status "completed", XP выдаётся в этом же ходу.
- Если chain и completed → сразу создай следующий квест (chain_order + 1).
- Не продлевай завершённый. Новый этап = новый квест.
- Максимум 8 активных.

LEVEL_HISTORY: массив {"level":2,"hp":"+4","stats":"+1 Сила","abilities":"+Рывок"}.

ПРОКАЧКА:
- xp >= xp_next → level+1, max_hp += 2+мод Тел, hp=max_hp, stats: одна хар +1, abilities: новое умение, skills: пересчёт при 5/9/13/17, xp_next: см. прогрессию.
- В level_history — запись.
- Max 1 уровень за ход.

RELATIONSHIPS: {"name":"Торвин","attitude":"насторожен","note":"помог"}. Максимум 6–8.

FACTION_CLOCKS: {"name":"Культ","progress":3,"max":6,"goal":"..."}. 1–4 силы.
"""


SUMMARY_PROMPT = """
Ты — архивариус. Сожми фрагмент диалога в краткое резюме.

СОХРАНИ:
- Ключевые события, имена NPC, отношение к игроку
- Решения и последствия
- Открытые вопросы, цели, долги
- Факты мира
- Расу, класс, предысторию, характеристики
- Текущий XP, уровень, активные квесты и их этапы
- Активные заметки (письма, документы — их суть)
- Текущее положение

НЕ ВКЛЮЧАЙ: дословные реплики, эмоции, повторы.

Формат: 1 плотный абзац, 4–6 предложений.
"""

DICE_RE = re.compile(r"^\s*(\d*)d(\d+)([+-]\d+)?\s*$", re.IGNORECASE)

DEFAULT_STATE = {
    "name": "Пустой", "race": "", "class": "", "background": "",
    "level": 1, "xp": 0, "xp_next": 100,
    "hp": 10, "max_hp": 10, "gold": 0,
    "stats": {"str": 10, "dex": 10, "con": 10, "int": 10, "wis": 10, "cha": 10},
    "proficiencies": [], "skills": [], "abilities": [],
    "inventory": [], "notes": [], "quests": [], "conditions": [],
    "relationships": [], "faction_clocks": [],
    "dc_modifier": 0, "dc_modifier_reasons": [],
    "position": "стоит", "cover": "нет",
    "weapon_in_hand": "", "restrained": False,
    "level_history": []
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
        f"{m['role']}: {m['content']}" for m in to_summarize if m.get("content")
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


def normalize_quest(q):
    if isinstance(q, dict):
        return q
    if isinstance(q, str):
        return {
            "id": "legacy-" + str(random.randint(1000, 9999)),
            "name": q, "type": "side", "status": "active",
            "chain": "", "chain_order": 0,
            "stages": [], "current_stage": 0,
            "rewards": {}, "giver": "", "location": ""
        }
    return None


def normalize_note(n):
    if isinstance(n, dict):
        # Проверка минимальных полей
        if "id" not in n:
            n["id"] = "n" + str(random.randint(1000, 9999))
        if "type" not in n:
            n["type"] = "note"
        if "title" not in n:
            n["title"] = (n.get("content", "") or "")[:40]
        if "content" not in n:
            n["content"] = ""
        if "unread" not in n:
            n["unread"] = True
        return n
    if isinstance(n, str):
        return {
            "id": "n" + str(random.randint(1000, 9999)),
            "type": "note", "title": n[:40], "content": n,
            "source": "", "date": "", "unread": True
        }
    return None


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
        for f in ("race", "class", "background", "position", "cover", "weapon_in_hand"):
            if not isinstance(merged.get(f), str):
                merged[f] = DEFAULT_STATE.get(f, "")
        if not isinstance(merged.get("restrained"), bool):
            merged["restrained"] = False
        for f in ("inventory", "notes", "quests", "conditions", "relationships",
                  "faction_clocks", "dc_modifier_reasons",
                  "proficiencies", "skills", "abilities", "level_history"):
            if not isinstance(merged.get(f), list):
                merged[f] = []
        merged["quests"] = [q for q in (normalize_quest(x) for x in merged["quests"]) if q]
        merged["notes"] = [n for n in (normalize_note(x) for x in merged["notes"]) if n]
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
            try:
                stream = client.chat.completions.create(
                    model=MODEL, messages=messages,
                    temperature=0.9,
                    frequency_penalty=FREQ_PENALTY,
                    presence_penalty=PRES_PENALTY,
                    stream=True,
                )
            except Exception as inner:
                msg = str(inner).lower()
                if "frequency_penalty" in msg or "presence_penalty" in msg or "unknown" in msg:
                    stream = client.chat.completions.create(
                        model=MODEL, messages=messages,
                        temperature=0.9, stream=True,
                    )
                else:
                    raise
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
