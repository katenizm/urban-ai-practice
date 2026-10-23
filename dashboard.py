"""
Сборка одной HTML-страницы dashboard.html из СОХРАНЁННЫХ результатов BlocksNet.

Скрипт только ЧИТАЕТ готовые файлы из папки data/ — он ничего не скачивает из
интернета и не повторяет расчёты. Интерактивная карта, графики и таблицы
собираются из данных, которые уже посчитаны в ноутбуке.

Запуск:
    python dashboard.py
Затем открой страницу через локальный сервер, чтобы браузер передавал Referer
для картографических тайлов:
    python -m http.server 8000
    http://localhost:8000/dashboard.html
"""

import base64
import io
import json
import re
from pathlib import Path

import folium
import geopandas as gpd
import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

DATA = Path("data")
OUT = Path("dashboard.html")
CRS_WGS = 4326
SIMPLIFY = 0.0007  # единое упрощение уменьшает вес интерактивных слоёв

try:
    plt.style.use("seaborn-v0_8-whitegrid")
except OSError:
    pass


# ------------------------------------------------------------------ чтение
def load(name, required=False):
    """Прочитать GeoJSON из data/. Никаких сетевых запросов."""
    path = DATA / f"{name}.geojson"
    if not path.exists():
        if required:
            raise FileNotFoundError(f"Нет файла {path}. Сначала выполните расчёты в ноутбуке.")
        print(f"  пропускаю {name}.geojson (нет файла)")
        return None
    return gpd.read_file(path).to_crs(CRS_WGS)


def simplified(gdf, columns):
    """Слой только с нужными колонками и облегчённой геометрией."""
    cols = [c for c in columns if c in gdf.columns]
    out = gdf[cols + ["geometry"]].copy()
    out["geometry"] = out.geometry.simplify(SIMPLIFY)
    return out


print("Читаю сохранённые результаты из", DATA.resolve())
blocks = load("blocks", required=True)
buildings = load("buildings_blocks")
schools = load("schools_blocks")
provision = load("provision")
density = load("density")
morphotypes = load("morphotypes")
area_acc = load("area_accessibility")
travel_time = load("travel_time")

links = None
links_path = DATA / "provision_links.csv"
if links_path.exists():
    links = pd.read_csv(links_path)


# --------------------------------------------------------------- графики
CATEGORY_TRANSLATIONS = {
    "agriculture": "сельское хозяйство", "business": "деловая функция",
    "industrial": "промышленная функция", "recreation": "рекреация",
    "residential": "жилая застройка", "special": "специальное назначение",
    "high-mid-rise high-density residential": "средне- и многоэтажная плотная жилая",
    "high-mid-rise residential": "средне- и многоэтажная жилая",
    "high-rise high-density residential": "высотная плотная жилая",
    "low-rise low-density mixed-use": "малоэтажная разреженная смешанная",
    "low-rise low-density non-residential": "малоэтажная разреженная нежилая",
    "low-rise low-density residential": "малоэтажная разреженная жилая",
    "mid-rise low-density non-residential": "среднеэтажная разреженная нежилая",
    "mid-rise low-density residential": "среднеэтажная разреженная жилая",
    "mid-rise residential": "среднеэтажная жилая",
    "central model": "центральная модель", "high-rise modern microdistrict": "высотный современный микрорайон",
    "high-rise soviet microdistrict": "высотный советский микрорайон",
    "individual residential": "индивидуальная жилая застройка", "low-rise model": "малоэтажная модель",
    "low-rise non-residential": "малоэтажная нежилая застройка", "mid-rise": "среднеэтажная застройка",
    "mid-rise block": "среднеэтажная квартальная застройка", "mid-rise non-residential": "среднеэтажная нежилая застройка",
}

METRIC_INFO = {
    "block_count": "Число кварталов в границах территории. Единица: квартал. Источник: геометрия из OpenStreetMap.",
    "land_use": "Преобладающая функция территории квартала. Категория определяется по тегам землепользования OpenStreetMap.",
    "population": "Оценка числа жителей квартала по площади и этажности зданий. Единица: человек. Источник: модель BlocksNet.",
    "building_count": "Количество зданий, попавших в границы квартала. Единица: здание. Источник: OpenStreetMap.",
    "capacity": "Расчётная вместимость школ в квартале. Единица: место. Часть значений оценена моделью BlocksNet.",
    "provision_strong": "Доля потребности в школьных местах, покрытая в пределах нормативной доступности (15 минут). Диапазон: 0–1.",
    "provision_weak": "Доля потребности в школьных местах с учётом объектов до 45 минут пути. Диапазон: 0–1.",
    "demand_left": "Расчётный дефицит школьных мест после распределения доступной вместимости. Единица: место.",
    "capacity_left": "Остаток школьных мест после распределения спроса. Единица: место.",
    "fsi": "Интенсивность использования территории: площадь всех этажей, делённая на площадь квартала. Безразмерный показатель.",
    "gsi": "Доля площади квартала, занятая застройкой. Диапазон: 0–1.",
    "mxi": "Доля жилой площади в общей площади этажей. Диапазон: 0–1; рассчитывается для кварталов со зданиями.",
    "l": "Средняя этажность: площадь этажей, делённая на площадь застройки. Единица: этаж.",
    "osr": "Соотношение открытых пространств и площади этажей. Безразмерный показатель.",
    "spacematrix": "Тип застройки по кластеризации показателей этажности, интенсивности и доли жилья.",
    "strelka": "Тип застройки по классификации «Стрелка» на основе порогов этажности и плотности.",
    "area_accessibility": "Средневзвешенное по площади время в пути от квартала. Единица: минута; меньшее значение означает более высокую доступность.",
    "travel_time_mean": "Среднее время пути от квартала к другим кварталам по пешеходному графу OpenStreetMap. Единица: минута.",
}

KPI_INFO_KEYS = {
    "Кварталов": "block_count", "Население (оценка)": "population",
    "Средний FSI": "fsi", "Доступность, мин": "area_accessibility",
    "Школ": "capacity", "Нехватка мест": "demand_left",
}

CHART_INFO_KEYS = {
    "Функции кварталов": "land_use", "Население по кварталам": "population",
    "Число зданий на квартал": "building_count", "Вместимость школ": "capacity",
    "Обеспеченность школами: strong": "provision_strong",
    "Обеспеченность школами: weak": "provision_weak",
    "Нехватка школьных мест": "demand_left", "Плотность застройки FSI": "fsi",
    "Доля земли под застройкой GSI": "gsi", "Доля жилья MXI": "mxi", "Этажность L": "l",
    "Типы застройки — Spacematrix": "spacematrix", "Типы застройки — «Стрелка»": "strelka",
    "Доступность с учётом площади": "area_accessibility", "Среднее время в пути": "travel_time_mean",
}


def bilingual_category(value):
    raw = str(value)
    translated = CATEGORY_TRANSLATIONS.get(raw.lower())
    return f"{translated} ({raw})" if translated else raw


def png(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=120, bbox_inches="tight")
    plt.close(fig)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def _clean(fig):
    for spine in ("top", "right"):
        fig.axes[0].spines[spine].set_visible(False)
    fig.tight_layout()
    return png(fig)


def fig_hist(series, title, xlabel, color="#88A2FF", bins=30, clip=None):
    s = series.replace([float("inf"), float("-inf")], pd.NA).dropna()
    if clip is not None:
        s = s[s <= clip]
    fig, ax = plt.subplots(figsize=(6.5, 3.8))
    s.plot(kind="hist", bins=bins, ax=ax, color=color, edgecolor="white")
    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.set_ylabel("Число кварталов")
    return _clean(fig)


def fig_bar_counts(series, title, ylabel, color="#AB9DFF", top=None, rot=45):
    data = series.value_counts(dropna=False)
    if top:
        data = data.head(top)
    data.index = [bilingual_category(value) for value in data.index]
    fig, ax = plt.subplots(figsize=(6.5, 5.8 if rot >= 80 else 3.8))
    data.plot(kind="bar", ax=ax, color=color, edgecolor="white")
    ax.set_title(title)
    ax.set_ylabel(ylabel)
    ax.set_xlabel("")
    ax.tick_params(axis="x", rotation=rot, labelsize=8 if rot >= 80 else 9)
    return _clean(fig)


charts = []
if "land_use" in blocks.columns:
    charts.append(("Функции кварталов",
                   "Сколько кварталов имеют каждую преобладающую функцию (тег landuse из OSM).",
                   fig_bar_counts(blocks["land_use"], "Преобладающая функция", "Число кварталов", "#88A2FF")))
if buildings is not None:
    charts.append(("Население по кварталам",
                   "Распределение кварталов по оценке населения (модель BlocksNet), человек.",
                   fig_hist(buildings["population"], "Население квартала, чел.", "Человек на квартал", "#253A82", clip=6000)))
    charts.append(("Число зданий на квартал",
                   "Сколько зданий OSM попало в каждый квартал, шт.",
                   fig_hist(buildings["count"], "Здания на квартал, шт.", "Зданий на квартал", "#AB9DFF", clip=60)))
if schools is not None:
    charts.append(("Вместимость школ",
                   "Оценка вместимости школ по кварталам, мест (значительная часть — оценка модели).",
                   fig_hist(schools["capacity"], "Вместимость квартала, мест", "Мест в школах квартала", "#FFB2F7", clip=1500)))
if provision is not None:
    charts.append(("Обеспеченность школами: strong",
                   "Доля потребности, покрытая местами в пределах нормативной доступности (15 мин), 0–1.",
                   fig_hist(provision["provision_strong"], "provision_strong", "Доля обеспеченности", "#253A82", bins=20)))
    charts.append(("Обеспеченность школами: weak",
                   "То же, но с учётом мест дальше норматива (до 45 мин), 0–1.",
                   fig_hist(provision["provision_weak"], "provision_weak", "Доля обеспеченности", "#88A2FF", bins=20)))
    charts.append(("Нехватка школьных мест",
                   "Сколько мест не хватает каждому кварталу (demand_left), мест.",
                   fig_hist(provision["demand_left"], "Нехватка мест", "Не хватает мест", "#FFB2F7", clip=3000)))
if density is not None:
    built = density[density["count"] > 0]
    charts.append(("Плотность застройки FSI",
                   "FSI = площадь этажей / площадь квартала (безразмерный).",
                   fig_hist(density["fsi"], "FSI", "FSI", "#253A82", clip=6)))
    charts.append(("Доля земли под застройкой GSI",
                   "GSI = площадь застройки / площадь квартала, доля 0–1.",
                   fig_hist(density["gsi"], "GSI", "GSI", "#88A2FF", clip=1)))
    charts.append(("Доля жилья MXI",
                   "MXI = жилая площадь / площадь этажей, доля 0–1 (только кварталы со зданиями).",
                   fig_hist(built["mxi"], "MXI", "MXI", "#AB9DFF", clip=1)))
    charts.append(("Этажность L",
                   "L = площадь этажей / площадь застройки, этажей (только кварталы со зданиями).",
                   fig_hist(built["l"], "L, этажей", "Этажей", "#253A82", clip=25)))
if morphotypes is not None and "spacematrix" in morphotypes.columns:
    charts.append(("Типы застройки — Spacematrix",
                   "Группы k-means по l, fsi, mxi (название = этажность + плотность + жильё).",
                   fig_bar_counts(morphotypes["spacematrix"], "Тип (Spacematrix)", "Число кварталов", "#AB9DFF", rot=90)))
if morphotypes is not None and "strelka" in morphotypes.columns:
    charts.append(("Типы застройки — «Стрелка»",
                   "Классификация по правилам (пороги этажности и плотности).",
                   fig_bar_counts(morphotypes["strelka"], "Тип («Стрелка»)", "Число кварталов", "#88A2FF", rot=90)))
if area_acc is not None:
    charts.append(("Доступность с учётом площади",
                   "Средневзвешенное по площади время в пути от квартала, минуты (меньше — лучше доступность).",
                   fig_hist(area_acc["area_accessibility"], "area_accessibility, мин", "Минут", "#FFB2F7", clip=350)))
if travel_time is not None:
    charts.append(("Среднее время в пути",
                   "Среднее время в пути от квартала к другим, минуты (по пешеходному графу OSM).",
                   fig_hist(travel_time["travel_time_mean"], "travel_time_mean, мин", "Минут", "#253A82", clip=350)))


# ------------------------------------------------------------------ карта
DEFAULT_LAYERS = {"land_use": ["land_use"]}
# Официальный HTTPS URL OSM и обязательная видимая атрибуция.
m = folium.Map(
    tiles="https://tile.openstreetmap.org/{z}/{x}/{y}.png",
    attr='© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>',
)

layers = [
    # (данные, колонка, подпись слоя, cmap, категориальный, мин, макс)
    (blocks, "land_use", "Функция квартала (OSM)", None, True, None, None),
    (buildings, "population", "Население, чел. (оценка)", "YlOrRd", False, None, None),
    (buildings, "count", "Зданий на квартал, шт.", "Blues", False, None, None),
    (schools, "capacity", "Вместимость школ, мест (оценка)", "PuBuGn", False, None, None),
    (provision, "provision_strong", "Обеспеченность strong (0–1)", "RdYlGn", False, 0, 1),
    (provision, "provision_weak", "Обеспеченность weak (0–1)", "RdYlGn", False, 0, 1),
    (provision, "demand_left", "Нехватка мест, шт.", "Reds", False, None, None),
    (provision, "capacity_left", "Остатки мест, шт.", "Greens", False, None, None),
    (density, "fsi", "Плотность FSI", "viridis", False, None, None),
    (density, "gsi", "Занятость земли GSI", "viridis", False, 0, 1),
    (density, "mxi", "Доля жилья MXI", "viridis", False, 0, 1),
    (density, "l", "Этажность L", "viridis", False, None, None),
    (density, "osr", "Открытые пространства OSR", "viridis", False, None, 30),
    (morphotypes, "spacematrix", "Тип застройки (Spacematrix)", None, True, None, None),
    (morphotypes, "strelka", "Тип застройки («Стрелка»)", None, True, None, None),
    (area_acc, "area_accessibility", "Доступность по площади, мин", "RdYlGn_r", False, None, None),
    (travel_time, "travel_time_mean", "Среднее время в пути, мин", "magma", False, None, None),
]

map_data = blocks.copy()
for source in (buildings, schools, provision, density, morphotypes, area_acc, travel_time):
    if source is None:
        continue
    for col in source.columns:
        if col != "geometry" and col not in map_data.columns:
            map_data[col] = source[col].values
map_data["block_id"] = map_data.index + 1
if "land_use" in map_data.columns:
    map_data["land_use_label"] = map_data["land_use"].map(bilingual_category)
map_data = simplified(map_data, list(map_data.columns.drop("geometry")))
minx, miny, maxx, maxy = map_data.total_bounds
m.fit_bounds([[miny, minx], [maxy, maxx]])
land_colors = {"agriculture": "#C0E0FF", "business": "#88A2FF", "industrial": "#253A82",
               "recreation": "#E3FC87", "residential": "#FFB2F7", "special": "#AB9DFF"}
geo_layer = folium.GeoJson(
    map_data.to_json(), name="Кварталы",
    style_function=lambda feature: {"color": "#253A82", "weight": 0.8,
                                    "fillColor": land_colors.get(str(feature["properties"].get("land_use")), "#E8ECF8"),
                                    "fillOpacity": 0.88},
    highlight_function=lambda feature: {"weight": 2, "color": "#253A82", "fillOpacity": 0.96},
    tooltip=folium.GeoJsonTooltip(fields=["block_id", "land_use_label"],
                                  aliases=["Квартал №", "Функция"],
                                  labels=True, sticky=True),
).add_to(m)

map_options = []
for gdf, col, label, cmap, categorical, vmin, vmax in layers:
    if gdf is None or col not in map_data.columns:
        continue
    series = map_data[col]
    if categorical:
        values = sorted(series.dropna().astype(str).unique().tolist())
        lo, hi = 0, max(len(values) - 1, 1)
    else:
        numeric = pd.to_numeric(series, errors="coerce").replace([float("inf"), float("-inf")], pd.NA).dropna()
        lo = float(vmin if vmin is not None else (numeric.quantile(.02) if len(numeric) else 0))
        hi = float(vmax if vmax is not None else (numeric.quantile(.98) if len(numeric) else 1))
        values = []
    map_options.append({"field": col, "label": label, "info_key": ("building_count" if col == "count" else col), "categorical": categorical,
                        "min": lo, "max": hi, "values": values,
                        "display_values": [bilingual_category(value) for value in values]})
m.height = [600, "px"]
m.width = ["100%", "%"]
print("Показателей на карте:", len(map_options))


# ---------------------------------------------------------------- числа (KPI)
def num(x, nd=0):
    return f"{x:,.{nd}f}".replace(",", " ")


kpi = [("Кварталов", num(len(blocks)), "в границах территории")]
if buildings is not None:
    kpi.append(("Население (оценка)", num(buildings["population"].sum()), "чел., модель BlocksNet"))
if schools is not None:
    kpi.append(("Школ", num(int(schools["count"].sum())), f"{num(schools['capacity'].sum())} мест"))
if provision is not None:
    kpi.append(("Нехватка мест", num(provision["demand_left"].sum()),
                f"при спросе {num(provision['demand'].sum())}"))
if density is not None:
    kpi.append(("Средний FSI", f"{density['fsi'].mean():.2f}", "площадь этажей / участок"))
if area_acc is not None:
    kpi.append(("Доступность, мин", f"{area_acc['area_accessibility'].mean():.1f}", "средневзвеш. по площади"))

kpi_by_name = {name: (value, subtitle) for name, value, subtitle in kpi}


def kpi_group(number, title, subtitle, names):
    metrics = []
    for name in names:
        if name not in kpi_by_name:
            continue
        value, note = kpi_by_name[name]
        info_key = KPI_INFO_KEYS.get(name, "")
        metrics.append(
            f'<div class="metric"><div class="metric-value">{value}</div>'
            f'<div class="metric-name" data-metric-info="{info_key}">{name}</div><div class="metric-note">{note}</div></div>'
        )
    if not metrics:
        return ""
    return (
        f'<section class="kpi-group"><div class="group-heading"><span class="group-number">{number}</span>'
        f'<div><h3>{title}</h3><p>{subtitle}</p></div></div>'
        f'<div class="group-metrics">{"".join(metrics)}</div></section>'
    )


kpi_html = "".join([
    kpi_group("01", "Масштаб города", "Квартальная структура и население", ["Кварталов", "Население (оценка)"]),
    kpi_group("02", "Застройка и доступность", "Интенсивность и время в пути", ["Средний FSI", "Доступность, мин"]),
    kpi_group("03", "Обеспеченность школами", "Спрос, вместимость и дефицит мест", ["Школ", "Нехватка мест"]),
])


# --------------------------------------------------------------- таблицы
def stats_section(title, mapping):
    rows = []
    for name, series in mapping.items():
        s = series.replace([float("inf"), float("-inf")], pd.NA).dropna()
        rows.append({"Показатель (ед.)": name, "Мин.": s.min(), "Среднее": s.mean(),
                     "Медиана": s.median(), "Макс.": s.max()})
    return title, pd.DataFrame(rows).set_index("Показатель (ед.)").round(2)


sections = []
if all(c in blocks.columns for c in ["residential", "business", "recreation", "industrial",
                                     "transport", "special", "agriculture"]):
    sections.append(("Землепользование — доли площадей (0–1), средние по кварталам",
                     pd.DataFrame({
                         "Функция": ["Жильё", "Бизнес", "Рекреация", "Промышленность",
                                     "Транспорт", "Особые", "Сельское хозяйство", "Доля главной функции"],
                         "Средняя доля": [blocks[c].mean() for c in
                                          ["residential", "business", "recreation", "industrial",
                                           "transport", "special", "agriculture", "share"]],
                     }).set_index("Функция").round(3)))
if buildings is not None:
    sections.append(stats_section("Здания и население (по кварталам)", {
        "Число зданий (шт.)": buildings["count"],
        "Площадь застройки (м²)": buildings["footprint_area"],
        "Сумма этажей (этажей)": buildings["number_of_floors"],
        "Площадь этажей (м²)": buildings["build_floor_area"],
        "Жилая площадь (м²)": buildings["living_area"],
        "Нежилая площадь (м²)": buildings["non_living_area"],
        "Население, оценка (чел.)": buildings["population"],
    }))
if schools is not None:
    mapping = {"Число школ (шт.)": schools["count"], "Вместимость (мест)": schools["capacity"]}
    if "capacity_estimated_value" in schools.columns:
        mapping["Вместимость оценённая (мест)"] = schools["capacity_estimated_value"]
    sections.append(stats_section("Школы (по кварталам)", mapping))
if provision is not None:
    sections.append(stats_section("Обеспеченность школами (по кварталам)", {
        "Потребность в местах (мест)": provision["demand"],
        "Места школ (мест)": provision["capacity"],
        "Нехватка мест (мест)": provision["demand_left"],
        "Покрыто в норме, demand_within (мест)": provision["demand_within"],
        "Покрыто вне нормы, demand_without (мест)": provision["demand_without"],
        "Остатки мест (мест)": provision["capacity_left"],
        "Обеспеченность strong (доля 0–1)": provision["provision_strong"],
        "Обеспеченность weak (доля 0–1)": provision["provision_weak"],
    }))
if density is not None:
    built = density[density["count"] > 0]
    sections.append(stats_section("Плотность застройки (кварталы со зданиями)", {
        "Площадь квартала site_area (м²)": density["site_area"],
        "FSI, интенсивность (безразм.)": density["fsi"],
        "GSI, доля земли (0–1)": density["gsi"],
        "MXI, доля жилья (0–1)": built["mxi"],
        "L, этажность (этажей)": built["l"],
        "OSR, открытые пространства (безразм.)": built["osr"],
        "Жилая площадь / застройка (безразм.)": built["share_living"],
        "Нежилая площадь / застройка (безразм.)": built["share_non_living"],
    }))
if area_acc is not None or travel_time is not None:
    mapping = {}
    if area_acc is not None:
        mapping["Доступность по площади (мин)"] = area_acc["area_accessibility"]
    if travel_time is not None:
        mapping["Среднее время в пути (мин)"] = travel_time["travel_time_mean"]
    sections.append(stats_section("Доступность (по кварталам)", mapping))

def table_group_rank(title):
    title = title.lower()
    if "школ" in title or "обеспеченность" in title:
        return 2
    if "плотность" in title or "доступность" in title:
        return 1
    return 0

sections.sort(key=lambda section: table_group_rank(section[0]))

dictionary = pd.DataFrame(
    [
        ("residential … agriculture", "Доля площади квартала под каждой функцией", "доля 0–1", "данные OSM"),
        ("land_use, share", "Преобладающая функция квартала и её доля", "категория / доля", "данные OSM"),
        ("population", "Население квартала (по площади и этажности зданий)", "человек", "оценка модели"),
        ("footprint_area, build_floor_area", "Площадь застройки и площадь всех этажей", "м²", "данные + расчёт"),
        ("number_of_floors, l", "Этажность зданий (L — средняя по кварталу)", "этажей", "данные / оценка"),
        ("living_area, non_living_area", "Жилая и нежилая площадь", "м²", "оценка модели"),
        ("count (здания)", "Число зданий в квартале", "шт.", "расчёт"),
        ("capacity", "Вместимость школ квартала", "мест", "данные / оценка"),
        ("demand", "Потребность в местах = население × 120/1000", "мест", "оценка (норматив)"),
        ("provision_strong", "Доля потребности, покрытая в пределах нормативной доступности (15 мин)", "доля 0–1", "расчёт"),
        ("provision_weak", "То же, но с учётом мест дальше норматива (до 45 мин)", "доля 0–1", "расчёт"),
        ("demand_left, capacity_left", "Нехватка мест и неиспользованные места", "мест", "расчёт"),
        ("demand_within/without, capacity_within/without", "Спрос и места в пределах / вне норматива", "мест", "расчёт"),
        ("fsi", "Интенсивность застройки = площадь этажей / площадь квартала", "безразмерный", "расчёт"),
        ("gsi", "Доля земли под застройкой = застройка / площадь квартала", "доля 0–1", "расчёт"),
        ("mxi", "Доля жилья = жилая площадь / площадь этажей", "доля 0–1", "расчёт"),
        ("osr", "Открытые пространства на единицу площади этажей", "безразмерный", "расчёт"),
        ("share_living, share_non_living", "Жилая / нежилая площадь на единицу застройки", "безразмерный", "расчёт"),
        ("spacematrix", "Тип застройки (кластеризация по l, fsi, mxi)", "категория", "расчёт"),
        ("strelka", "Тип застройки (правила по l, fsi, mxi)", "категория", "расчёт"),
        ("area_accessibility", "Средневзвешенное по площади время в пути от квартала", "минуты", "расчёт"),
        ("travel_time_mean", "Среднее время в пути от квартала к другим", "минуты", "расчёт по графу OSM"),
    ],
    columns=["Показатель", "Что означает", "Единицы", "Источник"],
)

# пример по кварталам
frames = [blocks[["land_use", "share"]]]
for src in (buildings, schools, provision, density, morphotypes, area_acc, travel_time):
    if src is not None:
        frames.append(src.drop(columns="geometry", errors="ignore"))
sample = pd.concat(frames, axis=1)
sample = sample.loc[:, ~sample.columns.duplicated()].head(15)
for col in ("land_use", "spacematrix", "strelka"):
    if col in sample.columns:
        position = sample.columns.get_loc(col) + 1
        sample.insert(position, f"{col} · перевод", sample[col].map(bilingual_category))

links_html = ""
if links is not None and not links.empty:
    top_links = links.sort_values("value", ascending=False).head(15)
    links_html = f"""
  <details class="data-panel"><summary>Распределение спроса между кварталами<span>Показать 15 крупнейших связей</span></summary>
  <p class="muted">Квартал-получатель (<code>source</code>) получает места из квартала школ
     (<code>target</code>); <code>value</code> — сколько мест, шт. Всего связей:
     {len(links):,} · распределено мест: {num(links['value'].sum())}.</p>
  <div class="tablewrap">""".replace(",", " ") + top_links.to_html(index=False) + "</div>"
    links_html += "<p class='table-takeaway'><b>Короткий вывод.</b> В таблице показаны 15 связей с наибольшим объёмом распределённого спроса; это не полный список связей.</p></details>"


# ---------------------------------------------------------------- выводы
conclusions = ["<ul>"]
if "land_use" in blocks.columns:
    top_land = blocks["land_use"].value_counts().idxmax()
    conclusions.append(f"<li>Самая частая функция кварталов — <b>{top_land}</b>.</li>")
if buildings is not None:
    conclusions.append(
        f"<li>Оценка населения — <b>{num(buildings['population'].sum())} чел.</b> "
        "Это модельная оценка BlocksNet (по площади и этажности), не перепись.</li>")
if schools is not None and provision is not None:
    share_good = (provision["provision_strong"].fillna(0) >= 1).mean() * 100
    conclusions.append(
        f"<li>Школы дают <b>{num(schools['capacity'].sum())} мест</b> при спросе "
        f"<b>{num(provision['demand'].sum())}</b>; полностью обеспечены (strong ≥ 1) "
        f"<b>{share_good:.0f}%</b> кварталов, нехватка — <b>{num(provision['demand_left'].sum())} мест</b>.</li>")
if density is not None:
    conclusions.append(
        f"<li>Средний FSI = <b>{density['fsi'].mean():.2f}</b>, средняя этажность — "
        f"<b>{density.loc[density['count'] > 0, 'l'].mean():.1f} этажа</b>.</li>")
if area_acc is not None:
    conclusions.append(
        f"<li>Средняя доступность с учётом площади — <b>{area_acc['area_accessibility'].mean():.1f} мин</b> "
        "(меньше — квартал ближе к городу).</li>")
conclusions.append(
    '<li class="muted">Все показатели, помеченные «оценка», рассчитаны моделью; '
    "границы кварталов и функции — из OpenStreetMap и могут отличаться от официальных.</li>")
conclusions.append("</ul>")
conclusions = "".join(conclusions)


# ------------------------------------------------------ файлы и источники
file_names = {
    "blocks.geojson": "кварталы и землепользование",
    "buildings_blocks.geojson": "здания и население",
    "schools_blocks.geojson": "школы и вместимость",
    "provision.geojson": "обеспеченность школами",
    "provision_links.csv": "распределение спроса между кварталами",
    "density.geojson": "плотность застройки",
    "morphotypes.geojson": "типы застройки (Spacematrix, «Стрелка»)",
    "area_accessibility.geojson": "доступность с учётом площади",
    "travel_time.geojson": "время в пути по кварталам",
    "accessibility_matrix.csv": "матрица доступности между кварталами",
    "graph_walk.pkl": "пешеходный граф OSM",
}
files_list = "".join(
    f"<li>{file_names[p.name]} — <code>data/{p.name}</code></li>"
    for p in sorted(DATA.iterdir())
    if p.name in file_names
)


# ---------------------------------------------------------------- страница
def chart_takeaway(title):
    """Короткий вывод к диаграмме по сохранённому столбцу метрики."""
    def numeric(series):
        return pd.to_numeric(series, errors="coerce").replace([float("inf"), float("-inf")], pd.NA).dropna()

    def fmt(value, digits=1):
        return f"{value:,.{digits}f}".replace(",", " ").replace(".", ",")

    if title == "Функции кварталов":
        counts = blocks["land_use"].dropna().astype(str).value_counts()
        if len(counts):
            name = CATEGORY_TRANSLATIONS.get(counts.index[0].lower(), counts.index[0])
            return f"Чаще всего встречается функция «{name}» — {fmt(counts.iloc[0] / counts.sum() * 100)}% кварталов."
    if title == "Население по кварталам" and buildings is not None:
        values = numeric(buildings["population"])
        if len(values):
            median_note = " (во многих кварталах население не оценено)" if values.median() == 0 else ""
            return f"Медианная оценка — {fmt(values.median(), 0)} чел. на квартал{median_note}; средняя — {fmt(values.mean(), 0)} чел."
    if title == "Число зданий на квартал" and buildings is not None:
        values = numeric(buildings["count"])
        if len(values):
            return f"В {fmt((values == 0).mean() * 100)}% кварталов здания не обнаружены; медиана — {fmt(values.median(), 0)} зданий."
    if title == "Вместимость школ" and schools is not None:
        values = numeric(schools["capacity"])
        if len(values):
            return f"Школьные объекты внутри квартала не обнаружены в {fmt((values == 0).mean() * 100)}% случаев; медианная локальная вместимость — {fmt(values.median(), 0)} мест."
    if title.startswith("Обеспеченность школами:") and provision is not None:
        col = "provision_strong" if title.endswith("strong") else "provision_weak"
        values = numeric(provision[col])
        if len(values):
            return f"Полностью обеспечены (показатель ≥ 1) {fmt((values >= 1).mean() * 100)}% кварталов; средняя обеспеченность — {fmt(values.mean() * 100)}%."
    if title == "Нехватка школьных мест" and provision is not None:
        values = numeric(provision["demand_left"])
        if len(values):
            return f"Дефицит мест есть в {fmt((values > 0).mean() * 100)}% кварталов; медианный дефицит среди всех кварталов — {fmt(values.median(), 0)} мест."
    if title == "Плотность застройки FSI" and density is not None:
        values = numeric(density["fsi"])
        if len(values):
            return f"Медианный FSI — {fmt(values.median(), 2)}; средний — {fmt(values.mean(), 2)}."
    if title == "Доля земли под застройкой GSI" and density is not None:
        values = numeric(density["gsi"])
        if len(values):
            return f"Медианная доля квартала под застройкой — {fmt(values.median() * 100)}%; средняя — {fmt(values.mean() * 100)}%."
    if title == "Доля жилья MXI" and density is not None:
        values = numeric(density.loc[density["count"] > 0, "mxi"])
        if len(values):
            return f"Медианная доля жилой площади в площади этажей — {fmt(values.median() * 100)}% (кварталы со зданиями)."
    if title == "Этажность L" and density is not None:
        values = numeric(density.loc[density["count"] > 0, "l"])
        if len(values):
            return f"Медианная этажность — {fmt(values.median())} этажа; средняя — {fmt(values.mean())}."
    if title.startswith("Типы застройки") and morphotypes is not None:
        col = "spacematrix" if "Spacematrix" in title else "strelka"
        if col in morphotypes:
            counts = morphotypes[col].dropna().astype(str).value_counts()
            if len(counts):
                return f"Самый распространённый тип — «{bilingual_category(counts.index[0])}» ({fmt(counts.iloc[0] / counts.sum() * 100)}% классифицированных кварталов)."
    if title == "Доступность с учётом площади" and area_acc is not None:
        values = numeric(area_acc["area_accessibility"])
        if len(values):
            return f"Медианное время — {fmt(values.median())} мин; среднее — {fmt(values.mean())} мин."
    if title == "Среднее время в пути" and travel_time is not None:
        values = numeric(travel_time["travel_time_mean"])
        if len(values):
            return f"Медианное время — {fmt(values.median())} мин; среднее — {fmt(values.mean())} мин."
    return "Распределение показывает, насколько значения отличаются между кварталами."


chart_groups = {
    "Масштаб города": [],
    "Застройка и доступность": [],
    "Обеспеченность школами": [],
}
for title, caption, src in charts:
    if "школ" in title.lower() or "нехватка" in title.lower():
        group = "Обеспеченность школами"
    elif "доступность" in title.lower() or "время в пути" in title.lower():
        group = "Застройка и доступность"
    elif "население" in title.lower() or "число зданий" in title.lower():
        group = "Масштаб города"
    else:
        group = "Застройка и доступность"
    chart_groups[group].append(
        f'<figure class="card"><img src="{src}" alt="{title}">'
        f'<figcaption><b data-metric-info="{CHART_INFO_KEYS.get(title, "")}">{title}.</b> {caption}</figcaption>'
        f'<div class="chart-takeaway"><b>Вывод.</b> {chart_takeaway(title)}</div></figure>'
    )
chart_groups_html = "".join(
    f'<section class="chart-group"><div class="chart-group-heading"><span>{i:02d}</span>'
    f'<h3>{title}</h3></div><div class="grid">{"".join(items)}</div></section>'
    for i, (title, items) in enumerate(chart_groups.items(), start=1) if items
)
charts_html = "".join(
    f'<figure class="card"><img src="{src}" alt="{title}">'
    f'<figcaption><b>{title}.</b> {caption}</figcaption></figure>'
    for title, caption, src in charts
)

def table_takeaway(title, df):
    """Короткая интерпретация агрегатов, уже показанных в таблице."""
    if "Средняя доля" in df.columns and "Землепользование" in title:
        land_use = df.drop(index=[idx for idx in df.index if "главной функции" in str(idx).lower()], errors="ignore")
        values = pd.to_numeric(land_use["Средняя доля"], errors="coerce").dropna()
        if len(values):
            category = values.idxmax()
            return f"В среднем наибольшую долю площади квартала занимает «{category.lower()}» — {values.max() * 100:.1f}%."

    if "Среднее" not in df.columns:
        return "Таблица содержит исходные значения; смотрите определения показателей и единицы измерения в заголовках."

    def value_for(fragment, column="Среднее"):
        matches = [idx for idx in df.index if fragment.lower() in str(idx).lower()]
        if not matches or column not in df.columns:
            return None
        value = pd.to_numeric(pd.Series([df.loc[matches[0], column]]), errors="coerce").iloc[0]
        return None if pd.isna(value) else float(value)

    if "Здания и население" in title:
        pop = value_for("Население")
        peak = value_for("Население", "Макс.")
        if pop is not None:
            return f"Средняя оценка населения — {num(pop)} чел. на квартал; максимум среди кварталов — {num(peak or 0)} чел."
    if "Школы" in title:
        capacity = value_for("Вместимость")
        peak = value_for("Вместимость", "Макс.")
        if capacity is not None:
            return f"В среднем на квартал приходится {num(capacity)} мест; максимум — {num(peak or 0)} мест."
    if "Обеспеченность" in title:
        deficit, demand = value_for("Нехватка мест"), value_for("Потребность")
        strong = value_for("Обеспеченность strong")
        parts = []
        if deficit is not None:
            parts.append(f"средний дефицит — {num(deficit)} мест на квартал")
        if deficit is not None and demand:
            parts.append(f"это {deficit / demand * 100:.1f}% средней потребности")
        if strong is not None:
            parts.append(f"средняя обеспеченность в пределах норматива — {strong * 100:.1f}%")
        if parts:
            return "; ".join(parts).capitalize() + "."
    if "Плотность" in title:
        fsi, gsi = value_for("FSI"), value_for("GSI")
        if fsi is not None:
            detail = f" Средняя доля земли под застройкой — {(gsi or 0) * 100:.1f}%." if gsi is not None else ""
            return f"Средний FSI по кварталам — {fsi:.2f}.{detail}"
    if "Доступность" in title:
        access = value_for("Доступность по площади")
        if access is None:
            access = value_for("Среднее время в пути")
        if access is not None:
            return f"Среднее время в пути по кварталам — {access:.1f} мин; меньшее значение означает более высокую доступность."
    return "В таблице приведены минимум, среднее, медиана и максимум по кварталам."

sections_html = "".join(
    f"<details class='data-panel'><summary>{title}<span>Показать таблицу</span></summary>"
    f"<div class='tablewrap'>{df.to_html()}</div>"
    f"<p class='table-takeaway'><b>Короткий вывод.</b> {table_takeaway(title, df)}</p></details>" for title, df in sections
)

style = """
<style>
  :root { --ink:#253A82; --muted:#52618A; --line:#E7ECF8; --paper:#fff; --canvas:#F8FAFF;
          --accent:#FFB2F7; --blue:#88A2FF; --lav:#AB9DFF; --shadow:0 8px 28px rgba(37,58,130,.08); }
  * { box-sizing:border-box; }
  html { scroll-behavior:smooth; scroll-padding-top:86px; }
  body { margin:0; color:var(--ink); background:var(--canvas); font-family:Inter,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }
  header { background:rgba(255,255,255,.94); border-bottom:1px solid var(--line); position:sticky; top:0; z-index:1000;
           backdrop-filter:blur(16px); padding:0 max(24px,calc((100vw - 1460px)/2)); min-height:72px;
           display:flex; align-items:center; justify-content:space-between; gap:24px; }
  header h1 { margin:0; font-size:18px; letter-spacing:-.035em; font-weight:750; }
  header .sub { color:var(--muted); font-size:12px; margin-top:3px; }
  .topnav { display:flex; gap:7px; align-items:center; }
  .topnav a { color:#5c5b65; text-decoration:none; font-size:12px; padding:10px 13px; border-radius:24px; }
  .topnav a:hover { color:var(--ink); background:#F1F5FF; }
  .wrap { max-width:1500px; margin:0 auto; padding:28px 32px 72px; }
  .intro { display:flex; align-items:flex-end; justify-content:space-between; gap:20px; margin:4px 0 22px; }
  .eyebrow { color:var(--accent); text-transform:uppercase; letter-spacing:.12em; font-size:10px; font-weight:750; }
  .intro h2 { margin:5px 0 3px; font-size:30px; letter-spacing:-.05em; border:0; padding:0; }
  .intro p { margin:0; color:var(--muted); font-size:13px; }
  .kpis { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:13px; margin:0 0 24px; }
  .map-dashboard-grid { display:grid; grid-template-columns:minmax(0,1.8fr) minmax(300px,.9fr); gap:18px; align-items:stretch; margin:24px 0 34px; }
  .map-dashboard-grid h2 { margin-top:0; }
  .map-primary, .map-metrics { min-width:0; }
  .map-metrics { display:flex; flex-direction:column; }
  .map-metrics .kpis { flex:1; grid-template-columns:1fr; grid-template-rows:repeat(3,minmax(0,1fr)); gap:11px; margin:0; }
  .map-metrics .kpi-group { display:flex; flex-direction:column; justify-content:space-between; padding:15px 16px 13px; min-height:0; }
  .map-metrics .group-metrics { margin-top:12px; gap:9px; }
  .map-metrics .metric-value { font-size:20px; }
  .kpi-group { background:var(--paper); border:1px solid var(--line); border-radius:18px; padding:18px 19px 16px;
               box-shadow:var(--shadow); min-width:0; position:relative; overflow:hidden; }
  .kpi-group:after { content:""; position:absolute; width:85px; height:85px; right:-34px; top:-39px; border-radius:50%; background:linear-gradient(135deg,#ffe0e8,#e9e5ff); opacity:.65; }
  .group-heading { display:flex; gap:10px; align-items:flex-start; position:relative; z-index:1; min-height:42px; }
  .group-number { color:var(--ink); background:#FCE8FA; border-radius:8px; padding:5px 7px; font-size:10px; font-weight:750; }
  .group-heading h3 { margin:1px 0 3px; font-size:13px; font-weight:720; letter-spacing:-.02em; }
  .group-heading p { margin:0; font-size:10px; color:var(--muted); }
  .group-metrics { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:13px; margin-top:17px; }
  .metric { min-width:0; border-top:1px solid var(--line); padding-top:11px; }
  .metric-value { font-size:22px; letter-spacing:-.045em; font-weight:750; line-height:1.1; white-space:nowrap; }
  .metric-name { font-size:11px; font-weight:650; margin-top:6px; }
  .metric-name[data-metric-info], figcaption b[data-metric-info] { cursor:help; text-decoration:underline dotted #9AA9D2; text-underline-offset:3px; }
  .metric-tooltip { position:fixed; z-index:5000; width:min(330px,calc(100vw - 24px)); padding:12px 14px; border:1px solid #DCE4F7; border-radius:12px; background:#fff; color:var(--muted); box-shadow:0 12px 34px rgba(37,58,130,.18); font-size:11px; line-height:1.55; pointer-events:none; opacity:0; visibility:hidden; transition:opacity .12s ease; }
  .metric-tooltip.is-visible { opacity:1; visibility:visible; }
  .metric-tooltip strong { display:block; margin-bottom:4px; color:var(--ink); font-size:12px; }
  .metric-note { font-size:9px; color:var(--muted); margin-top:3px; line-height:1.35; }
  h2 { font-size:20px; letter-spacing:-.035em; margin:34px 0 13px; padding:0; border:0; }
  .note { background:var(--paper); border:1px solid var(--line); border-radius:16px; padding:16px 19px;
          font-size:13px; line-height:1.65; box-shadow:var(--shadow); }
  .source-note { margin:0 0 30px; padding:10px 13px; color:var(--muted); background:#F1F5FF; border:0; border-left:3px solid var(--blue); border-radius:0 10px 10px 0; box-shadow:none; font-size:11px; line-height:1.55; }
  .mapbox { border:1px solid var(--line); border-radius:18px; overflow:hidden; background:#fff; box-shadow:var(--shadow); }
  .map-toolbar { display:grid; grid-template-columns:max-content minmax(0,1fr); align-items:center; gap:10px 14px; padding:13px 16px; background:#fff; border-bottom:1px solid var(--line); }
  .map-toolbar label { grid-column:1; }
  .map-toolbar label { font-size:11px; color:var(--muted); font-weight:650; margin:0; }
  .map-toolbar select { grid-column:2; width:100%; max-width:480px; border:1px solid var(--line); border-radius:9px; padding:8px 34px 8px 11px; background:#faf9fb; color:var(--ink); font:inherit; font-size:12px; }
  .map-legend { grid-column:1/-1; justify-self:stretch; font-size:10px; color:var(--muted); display:grid; justify-items:end; gap:4px; }
  .legend-caption { font-size:10px; color:var(--muted); }
  .legend-scale { display:flex; align-items:center; gap:10px; font-variant-numeric:tabular-nums; }
  .legend-gradient { width:clamp(150px, 22vw, 260px); height:10px; border-radius:10px; background:linear-gradient(90deg,#C0E0FF,#88A2FF,#AB9DFF,#FFB2F7); }
  .legend-category-list { display:none; max-width:560px; justify-content:flex-end; flex-wrap:wrap; gap:6px 12px; font-size:10px; }
  .legend-category { display:inline-flex; align-items:center; gap:5px; white-space:nowrap; }
  .legend-swatch { width:10px; height:10px; border-radius:3px; border:1px solid #253A8240; }
  /* Монохромной делаем только картографическую подложку; кварталы остаются цветными. */
  .leaflet-tile-pane { filter: grayscale(1) brightness(1.12) contrast(.88); opacity:.32; }
  .mapbox .folium-map { height:540px !important; }
  .leaflet-control-layers { border:1px solid var(--line)!important; border-radius:12px!important; box-shadow:0 5px 22px #2221!important; }
  .leaflet-control-layers-expanded { padding:12px 14px!important; }
  .leaflet-control-layers label { font-size:12px; margin:5px 0; }
  .grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(310px,1fr)); gap:15px; }
  .chart-group { margin:16px 0 0; padding:16px; background:var(--paper); border:1px solid var(--line);
                 border-radius:17px; box-shadow:var(--shadow); }
  .chart-group-heading { display:flex; gap:9px; align-items:center; margin:0 0 13px; }
  .chart-group-heading span { color:var(--accent); background:#fff0f4; border-radius:7px; padding:5px 7px; font-size:9px; font-weight:750; }
  .chart-group-heading h3 { font-size:13px; font-weight:700; margin:0; }
  .card { background:var(--paper); border:1px solid var(--line); border-radius:17px; margin:0; padding:12px;
          box-shadow:var(--shadow); overflow:hidden; }
  .card img { width:100%; height:auto; display:block; border-radius:10px; }
  figcaption { font-size:11px; color:var(--muted); padding:9px 5px 3px; line-height:1.5; }
  figcaption b { display:block; color:var(--ink); font-size:13px; margin-bottom:2px; }
  .chart-takeaway { margin:8px 5px 3px; padding:9px 10px; border-left:3px solid var(--blue); border-radius:0 8px 8px 0;
                    background:#F5F7FF; color:#40527F; font-size:11px; line-height:1.5; }
  .chart-takeaway b { color:var(--ink); }
  .data-panel { background:var(--paper); border:1px solid var(--line); border-radius:15px; margin:10px 0;
                box-shadow:var(--shadow); overflow:hidden; }
  .data-panel summary { list-style:none; cursor:pointer; padding:15px 18px; font-size:13px; font-weight:650; }
  .data-panel summary::-webkit-details-marker { display:none; }
  .data-panel summary:after { content:"＋"; float:right; color:var(--accent); font-size:16px; line-height:12px; }
  .data-panel[open] summary:after { content:"−"; }
  .data-panel summary span { float:right; color:var(--muted); font-size:11px; font-weight:400; margin-right:24px; }
  table { border-collapse:collapse; width:100%; margin:0; font-size:11px; background:#fff; }
  th,td { border-bottom:1px solid var(--line); padding:9px 11px; text-align:right; white-space:nowrap; }
  th:first-child,td:first-child { text-align:left; }
  thead th { background:#faf9fb; position:sticky; top:0; font-weight:650; color:#595762; }
  .tablewrap { max-height:420px; overflow:auto; border-top:1px solid var(--line); }
  .table-takeaway { margin:0; padding:12px 16px 14px; color:var(--muted); font-size:11px; line-height:1.55; background:#F8FAFF; border-top:1px solid var(--line); }
  .table-takeaway b { color:var(--ink); }
  .table-tools { display:flex; align-items:center; gap:8px; flex-wrap:wrap; padding:10px 12px; background:#F8FAFF; border-bottom:1px solid var(--line); }
  .table-tools input { min-width:190px; flex:1; padding:8px 10px; border:1px solid var(--line); border-radius:8px; color:var(--ink); font:inherit; font-size:11px; background:white; }
  .table-tools button { padding:8px 11px; border:1px solid var(--line); border-radius:8px; background:white; color:var(--ink); font:inherit; font-size:11px; cursor:pointer; }
  .table-tools button:hover { background:#F1F5FF; }
  th[data-sortable] { cursor:pointer; }
  th[data-sortable]:hover { color:#253A82; }
  th[data-sortable]::after { content:' ↕'; color:#98A4C3; font-size:9px; }
  th[data-sortable][data-direction='asc']::after { content:' ↑'; color:#253A82; }
  th[data-sortable][data-direction='desc']::after { content:' ↓'; color:#253A82; }
  ul { line-height:1.8; padding-left:20px; }
  .muted { color:var(--muted); font-size:12px; }
  code { background:#f3f1f6; color:#605d69; padding:2px 5px; border-radius:5px; font-size:11px; }
  .section-label { margin:29px 0 12px; font-size:10px; text-transform:uppercase; letter-spacing:.12em; color:var(--muted); font-weight:750; }
  .page-footer { margin-top:38px; padding:22px 2px 4px; border-top:1px solid var(--line); display:flex; justify-content:space-between; gap:20px; flex-wrap:wrap; color:var(--muted); font-size:11px; line-height:1.7; }
  .page-footer strong { color:var(--ink); font-weight:650; }
  .footer-meta { text-align:right; }
  @media(max-width:980px) { .map-dashboard-grid { grid-template-columns:1fr; gap:22px; } }
  @media(max-width:760px) { header { padding:12px 18px; align-items:flex-start; flex-direction:column; gap:8px; }
    .topnav { overflow:auto; max-width:100%; } .topnav a { white-space:nowrap; padding:7px 10px; }
    .wrap { padding:22px 16px 48px; } .intro h2 { font-size:25px; } .kpis { grid-template-columns:1fr; }
    .map-toolbar { grid-template-columns:1fr; align-items:start; }
    .map-toolbar label, .map-toolbar select, .map-legend { grid-column:1; }
    .map-toolbar select { width:100%; max-width:100%; }
    .map-legend { width:100%; justify-items:start; }
    .legend-category-list { justify-content:flex-start; }
    .mapbox .folium-map { height:430px!important; } .grid { grid-template-columns:1fr; }
    .footer-meta { text-align:left; } }
</style>
"""

header_html = """
<header>
  <div><h1>Иркутск · городская среда</h1><div class="sub">Кварталы и пространственные показатели</div></div>
  <nav class="topnav"><a href="#overview">Обзор</a><a href="#map-section">Карта</a><a href="#charts">Показатели</a><a href="#tables">Данные</a></nav>
</header>
"""

content_html = f"""<div class="wrap">
  <section class="intro" id="overview"><div><div class="eyebrow">Городская аналитика · BlocksNet</div>
  <h2>Кварталы и метрики города</h2><p>Интерактивный обзор городской структуры, доступности и обеспеченности.</p></div></section>

  <div class="map-dashboard-grid">
    <section class="map-primary">
      <h2 id="map-section">Карта кварталов</h2>
      <p class="muted">Выберите показатель над картой. Наведите курсор на квартал, чтобы увидеть значение. Модельные значения отмечены как оценка.</p>
      <div class="mapbox"><div class="map-toolbar"><label for="metric-select">Цвет квартала показывает</label>
        <select id="metric-select">{''.join(f'<option value="{x["field"]}">{x["label"]}</option>' for x in map_options)}</select>
        <div class="map-legend"><span class="legend-caption" id="legend-caption"></span><div class="legend-scale"><span id="legend-min">Низкое</span><span class="legend-gradient"></span><span id="legend-max">Высокое</span></div><div class="legend-category-list" id="legend-categories"></div></div>
      </div><!--MAP--></div>
    </section>
    <section class="map-metrics" aria-label="Ключевые показатели города">
      <h2>Ключевые показатели</h2>
      <p class="muted">Сводка по всей территории исследования.</p>
      <div class="kpis">{kpi_html}</div>
    </section>
  </div>

  <div class="note source-note">
    <b>Данные и метод.</b> Слои построены по OpenStreetMap, расчёты выполнены библиотекой BlocksNet.
    Значения с пометкой «оценка» — модельные, а не статистические. Страница отображает сохранённые
    результаты и не скачивает данные и не повторяет расчёты.
  </div>

  <h2 id="charts">Показатели в распределении</h2>
  <p class="muted">Каждая диаграмма показывает распределение значений по кварталам; редкие экстремальные значения ограничены для читаемости.</p>
  {chart_groups_html}

  <h2>Краткие выводы</h2>
  <div class="note">{conclusions}</div>

  <h2 id="tables">Подробные таблицы</h2>
  <p class="muted">В таблицах доступны поиск по строкам, сортировка по нажатию на заголовок и выгрузка в CSV.</p>
{sections_html}

{links_html}

  <details class="data-panel"><summary>Пример значений по первым 15 кварталам<span>Показать таблицу</span></summary>
  <div class="tablewrap">{sample.to_html()}</div>
  <p class="table-takeaway"><b>Как читать.</b> Здесь приведены примеры строк, а не рейтинг кварталов и не репрезентативная выборка.</p></details>

  <h2>Ограничения и методика</h2>
  <div class="note">
    Границы кварталов и функции землепользования построены по OpenStreetMap и могут отличаться от
    официальных. Население и вместимость части школ — модельные оценки BlocksNet (по площади и
    этажности зданий). Время в пути рассчитано по пешеходному графу OSM без учёта расписаний
    транспорта. Показатели с бесконечными/неопределёнными значениями (например, OSR у кварталов
    без зданий) исключены из статистики.
  </div>
  <details class="data-panel"><summary>Словарь показателей<span>Показать определения</span></summary>
  <p class="muted">Что означает каждый показатель, в каких единицах измеряется и откуда берётся.</p>
  <div class="tablewrap">{dictionary.to_html(index=False)}</div>
  <p class="table-takeaway"><b>Как читать.</b> В словаре отмечено, какие значения взяты из OSM, рассчитаны по геометрии или являются модельными оценками.</p></details>

  <footer class="page-footer">
    <div><strong>Иркутск · городская среда</strong><br>Технологии ИИ в урбанистике · Екатерина Куманина</div>
    <div class="footer-meta">2026 · Источники: OpenStreetMap · BlocksNet<br>Дашборд отображает сохранённые результаты расчётов</div>
  </footer>
</div>"""


# ---------------------------------------------- вставка карты folium в страницу
page = m.get_root().render()
map_div = re.search(r'<div class="folium-map"[^>]*></div>', page).group(0)
body_start = page.find("<body>") + len("<body>")
map_extra = page[body_start: page.find(map_div)]
map_block = map_extra + map_div

page = page.replace(
    "</head>", "<title>Дашборд: кварталы и метрики Иркутска</title>" + style + "</head>", 1)
page = page.replace("</body>", content_html + "</body>", 1)
page = page.replace("<body>", "<body>" + header_html, 1)
page = page.replace("<!--MAP-->", map_block, 1)
page = page.replace(map_block, "", 1)  # убираем исходную копию блока карты в body

map_script = f"""
<script>
window.addEventListener('load', () => {{
(() => {{
  const options = {json.dumps(map_options, ensure_ascii=False)};
  const layer = {geo_layer.get_name()};
  const select = document.getElementById('metric-select');
  const low = document.getElementById('legend-min');
  const high = document.getElementById('legend-max');
  const caption = document.getElementById('legend-caption');
  const gradient = document.querySelector('.legend-gradient');
  const scale = document.querySelector('.legend-scale');
  const categoryList = document.getElementById('legend-categories');
  const metricLabel = document.querySelector('label[for="metric-select"]');
  const glossary = {json.dumps(METRIC_INFO, ensure_ascii=False)};
  const colors = ['#C0E0FF','#88A2FF','#AB9DFF','#FFB2F7','#E3FC87'];
  const categoryColors = ['#88A2FF','#E3FC87','#253A82','#FFB2F7','#C0E0FF','#AB9DFF'];
  function interpolate(t) {{
    t = Math.max(0, Math.min(1, t)); const x = t * (colors.length - 1), i = Math.floor(x), f = x - i;
    const a = colors[i].match(/[0-9a-f]{{2}}/gi).map(v => parseInt(v,16));
    const b = colors[Math.min(i+1,colors.length-1)].match(/[0-9a-f]{{2}}/gi).map(v => parseInt(v,16));
    return '#' + a.map((v,j) => Math.round(v+(b[j]-v)*f).toString(16).padStart(2,'0')).join('');
  }}
  function paint() {{
    const option = options.find(x => x.field === select.value); if (!option) return;
    metricLabel.dataset.metricInfo = option.info_key;
    select.dataset.metricInfo = option.info_key;
    caption.textContent = option.categorical
      ? 'Цвет показывает категорию квартала'
      : 'Значение по кварталу · ' + option.label + ' · слева меньше, справа больше';
    scale.style.display = option.categorical ? 'none' : 'flex';
    categoryList.style.display = option.categorical ? 'flex' : 'none';
    categoryList.replaceChildren();
    if (option.categorical) option.values.forEach((name, i) => {{
      const entry = document.createElement('span'); entry.className = 'legend-category';
      const swatch = document.createElement('span'); swatch.className = 'legend-swatch';
      swatch.style.background = categoryColors[i % categoryColors.length];
      entry.append(swatch, document.createTextNode(option.display_values[i] || name)); categoryList.appendChild(entry);
    }});
    low.textContent = option.categorical ? 'Категории' : Number(option.min).toLocaleString('ru-RU',{{maximumFractionDigits:1}});
    high.textContent = option.categorical ? 'по наведению' : Number(option.max).toLocaleString('ru-RU',{{maximumFractionDigits:1}});
    gradient.style.background = option.categorical
      ? 'linear-gradient(90deg,' + categoryColors.join(',') + ')'
      : 'linear-gradient(90deg,' + colors.join(',') + ')';
    layer.eachLayer(item => {{
      const props = item.feature.properties || {{}}, raw = props[option.field]; let fill = '#E8ECF8';
      if (raw !== null && raw !== undefined && raw !== '') {{
        if (option.categorical) {{ const idx = option.values.indexOf(String(raw)); fill = categoryColors[(idx < 0 ? 0 : idx) % categoryColors.length]; }}
        else {{ const n = Number(raw); if (Number.isFinite(n)) fill = interpolate((n-option.min)/(option.max-option.min || 1)); }}
      }}
      item.setStyle({{fillColor:fill, color:'#253A82', weight:.65, fillOpacity:.88}});
      item.off('mouseover'); item.off('mouseout');
      item.on('mouseover', () => item.setStyle({{color:'#253A82', weight:2, fillOpacity:.96}}));
      item.on('mouseout', () => item.setStyle({{fillColor:fill, color:'#253A82', weight:.65, fillOpacity:.88}}));
      let value = raw === null || raw === undefined ? 'нет данных' : (typeof raw === 'number' ? raw.toLocaleString('ru-RU',{{maximumFractionDigits:2}}) : String(raw));
      if (option.categorical && raw !== null && raw !== undefined) {{
        const categoryIndex = option.values.indexOf(String(raw));
        if (categoryIndex >= 0) value = option.display_values[categoryIndex] || value;
      }}
      item.unbindTooltip(); item.bindTooltip('<b>Квартал №' + (props.block_id || '—') + '</b><br>' + option.label + ': ' + value, {{sticky:true, opacity:.95}});
    }});
  }}
  select.addEventListener('change', paint); paint();
  const tooltip = document.createElement('div'); tooltip.className = 'metric-tooltip'; tooltip.setAttribute('role','tooltip');
  const tooltipTitle = document.createElement('strong'), tooltipText = document.createElement('span');
  tooltip.append(tooltipTitle, tooltipText); document.body.appendChild(tooltip);
  function placeTooltip(x,y) {{
    tooltip.style.left = Math.max(12, Math.min(x + 14, window.innerWidth - 342)) + 'px';
    tooltip.style.top = Math.max(12, Math.min(y + 14, window.innerHeight - tooltip.offsetHeight - 12)) + 'px';
  }}
  document.querySelectorAll('[data-metric-info]').forEach(target => {{
    const show = (x,y) => {{
      const key = target.dataset.metricInfo, description = glossary[key]; if (!description) return;
      tooltipTitle.textContent = target.textContent.trim().replace(/[.]+$/, '');
      tooltipText.textContent = description; tooltip.classList.add('is-visible'); placeTooltip(x,y);
    }};
    target.addEventListener('pointerenter', event => show(event.clientX,event.clientY));
    target.addEventListener('pointermove', event => {{ if (tooltip.classList.contains('is-visible')) placeTooltip(event.clientX,event.clientY); }});
    target.addEventListener('pointerleave', () => tooltip.classList.remove('is-visible'));
    target.addEventListener('focus', () => {{ const r = target.getBoundingClientRect(); show(r.left + r.width/2,r.bottom); }});
    target.addEventListener('blur', () => tooltip.classList.remove('is-visible'));
  }});
  document.querySelectorAll('.data-panel .tablewrap table').forEach((table, index) => {{
    const wrap = table.parentElement;
    const tools = document.createElement('div'); tools.className = 'table-tools';
    const search = document.createElement('input'); search.type = 'search';
    search.placeholder = 'Поиск в таблице'; search.setAttribute('aria-label', 'Поиск в таблице');
    const exportButton = document.createElement('button'); exportButton.type = 'button'; exportButton.textContent = 'Скачать CSV';
    tools.append(search, exportButton); wrap.insertBefore(tools, table);
    search.addEventListener('input', () => {{
      const query = search.value.trim().toLocaleLowerCase('ru-RU');
      table.querySelectorAll('tbody tr').forEach(row => {{ row.hidden = query && !row.textContent.toLocaleLowerCase('ru-RU').includes(query); }});
    }});
    table.querySelectorAll('thead th').forEach((th, column) => {{
      th.dataset.sortable = 'true'; th.title = 'Нажмите, чтобы сортировать';
      th.addEventListener('click', () => {{
        const body = table.tBodies[0]; if (!body) return;
        const ascending = th.dataset.direction !== 'asc';
        Array.from(body.rows).sort((a,b) => {{
          const av = (a.cells[column]?.textContent || '').trim().replace(/\\s/g,'').replace(',','.');
          const bv = (b.cells[column]?.textContent || '').trim().replace(/\\s/g,'').replace(',','.');
          const an = Number(av), bn = Number(bv);
          return (Number.isFinite(an) && Number.isFinite(bn) ? an-bn : av.localeCompare(bv,'ru')) * (ascending ? 1 : -1);
        }}).forEach(row => body.appendChild(row));
        table.querySelectorAll('thead th').forEach(cell => delete cell.dataset.direction);
        th.dataset.direction = ascending ? 'asc' : 'desc';
      }});
    }});
    exportButton.addEventListener('click', () => {{
      const rows = Array.from(table.rows).map(row => Array.from(row.cells).map(cell => '"' + cell.innerText.replace(/"/g,'""') + '"').join(','));
      const blob = new Blob(['\\ufeff' + rows.join('\\r\\n')], {{type:'text/csv;charset=utf-8'}});
      const link = document.createElement('a'); link.href = URL.createObjectURL(blob);
      link.download = 'dashboard-table-' + (index + 1) + '.csv'; link.click(); URL.revokeObjectURL(link.href);
    }});
  }});
}})();
}});
</script>
"""
# Ждём полной загрузки документа: Folium размещает скрипт GeoJSON после body.
page = page.replace("</body>", map_script + "</body>", 1)

OUT.write_text(page, encoding="utf-8")
print(f"Готово: {OUT.resolve()}  ({OUT.stat().st_size / 1e6:.1f} МБ)")
