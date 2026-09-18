import re
from difflib import SequenceMatcher
import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(page_title="Teslimat & Evrak Analiz Paneli", page_icon="📦", layout="wide")

# --------------------------------------------------------------------------------------
# YARDIMCI FONKSİYONLAR
# --------------------------------------------------------------------------------------

def find_col(df: pd.DataFrame, possible_names: list):
    """Verilen olası sütun isimlerinden Excel'de var olanı esnek şekilde bulur."""
    for target in possible_names:
        target_clean = target.strip().lower()
        for col in df.columns:
            if str(col).strip().lower() == target_clean:
                return col
        for col in df.columns:
            if target_clean in str(col).strip().lower():
                return col
    return None

def normalize_name(name) -> str:
    """Müşteri ismini standartlaştırır."""
    if pd.isna(name):
        return ""
    s = str(name).strip()
    s = s.replace("İ", "I").replace("ı", "i").upper()
    s = re.sub(r"[.,;:]", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()

@st.cache_data(show_spinner=False)
def build_canonical_map(all_names: list, threshold: float = 0.88) -> dict:
    """Benzer müşteri isimlerini eşleştirir."""
    unique_names = sorted(set(n for n in all_names if n), key=len, reverse=True)
    clusters = []
    for n in unique_names:
        placed = False
        for cluster in clusters:
            if SequenceMatcher(None, n, cluster[0]).ratio() >= threshold:
                cluster.append(n)
                placed = True
                break
        if not placed:
            clusters.append([n])
    mapping = {}
    for cluster in clusters:
        rep = max(cluster, key=len)
        for n in cluster:
            mapping[n] = rep
    return mapping

@st.cache_data(show_spinner=False)
def load_excel(file) -> pd.DataFrame:
    return pd.read_excel(file)

def pct(a, b):
    return round((a / b) * 100, 2) if b else 0.0

# --------------------------------------------------------------------------------------
# VERİ HAZIRLAMA (SADELEŞTİRİLMİŞ)
# --------------------------------------------------------------------------------------

def prepare_evrak_df(df: pd.DataFrame):
    col_musteri = find_col(df, ["Siparişi Veren Müş.", "Müşteri", "Musteri"])
    col_durum = find_col(df, ["Teslim Evrak Durum", "Durum", "Kargo Durumu", "Evrak Durumu"])

    if not col_musteri or not col_durum:
        st.error(f"Evrak dosyasında Müşteri veya Durum sütunu bulunamadı. Mevcut sütunlar: {list(df.columns)}")
        st.stop()

    out = pd.DataFrame()
    out["musteri_ham"] = df[col_musteri]
    out["musteri_norm"] = out["musteri_ham"].apply(normalize_name)
    out["evrak_durum"] = df[col_durum].astype(str).str.strip().str.upper()
    out["evrak_var"] = out["evrak_durum"].str.contains("VAR", na=False)
    return out

def prepare_zaman_df(df: pd.DataFrame):
    col_musteri = find_col(df, ["Siparişi Veren Müş.", "Müşteri", "Musteri"])
    col_durum = find_col(df, ["Durum", "Teslimat Durumu", "Kargo Durumu"])

    if not col_musteri or not col_durum:
        st.error(f"Zamanlama dosyasında Müşteri veya Durum sütunu bulunamadı. Mevcut sütunlar: {list(df.columns)}")
        st.stop()

    out = pd.DataFrame()
    out["musteri_ham"] = df[col_musteri]
    out["musteri_norm"] = out["musteri_ham"].apply(normalize_name)
    durum_norm = df[col_durum].astype(str).str.strip().str.upper()

    def kategori(d):
        if "GEÇ" in d or "GEC" in d:
            return "Geç"
        if "ERKEN" in d:
            return "Erken"
        if "ZAMAN" in d:
            return "Zamanında"
        return "Diğer"

    out["zaman_kategori"] = durum_norm.apply(kategori)
    return out

# --------------------------------------------------------------------------------------
# YORUM ÜRETİMİ
# --------------------------------------------------------------------------------------

def generate_commentary(musteri, evrak_oran, evrak_toplam, evrak_yok, zaman_oran, zaman_dagilim):
    lines = []

    if evrak_toplam > 0:
        if evrak_oran >= 90:
            seviye = "çok iyi"
        elif evrak_oran >= 75:
            seviye = "orta / iyileştirilebilir"
        else:
            seviye = "düşük (dikkat gerektiriyor)"
        lines.append(f"• **Evrak Performansı:** %{evrak_oran} evrak başarı oranı ile **{seviye}** seviyede. "
                     f"({evrak_toplam} kaydın {evrak_yok} tanesinde teslim evrakı eksik).")
    else:
        lines.append("• Bu müşteri için evrak verisi bulunamadı.")

    toplam_zaman = sum(zaman_dagilim.values())
    if toplam_zaman > 0:
        gec_oran = pct(zaman_dagilim.get("Geç", 0), toplam_zaman)
        if zaman_oran >= 85:
            zseviye = "yüksek"
        elif zaman_oran >= 70:
            zseviye = "makul"
        else:
            zseviye = "düşük"
        lines.append(f"• **Zaman Performansı:** Zamanında + erken teslimat oranı %{zaman_oran} ile **{zseviye}**. "
                     f"Teslimatların %{gec_oran}'i geç teslim edilmiş.")
    else:
        lines.append("• Bu müşteri için zamanlama verisi bulunamadı.")

    return "\n\n".join(lines)

# --------------------------------------------------------------------------------------
# ARAYÜZ
# --------------------------------------------------------------------------------------

st.title("📦 Teslimat Performans Analiz Paneli")

with st.sidebar:
    st.header("1️⃣ Dosyaları Yükle")
    file_evrak = st.file_uploader("Evrak Durumu Excel Dosyası", type=["xlsx", "xls"], key="evrak")
    file_zaman = st.file_uploader("Zamanlama Excel Dosyası", type=["xlsx", "xls"], key="zaman")

    st.header("2️⃣ Mod Seç")
    mode = st.radio(
        "Görüntüleme Modu",
        ["👤 Müşteri Analizi", "📄 Evrak Başarı Sıralaması", "⏱️ Zaman Başarı Sıralaması"],
    )

if not file_evrak or not file_zaman:
    st.info("Lütfen devam etmek için sol menüden her iki Excel dosyasını da yükleyin.")
    st.stop()

df_evrak_raw = load_excel(file_evrak)
df_zaman_raw = load_excel(file_zaman)

evrak = prepare_evrak_df(df_evrak_raw)
zaman = prepare_zaman_df(df_zaman_raw)

# Müşteri isimlerini normalize ederek eşleştir
all_norm_names = list(evrak["musteri_norm"]) + list(zaman["musteri_norm"])
canonical_map = build_canonical_map(all_norm_names, threshold=0.88)

evrak["musteri"] = evrak["musteri_norm"].map(canonical_map).fillna(evrak["musteri_norm"])
zaman["musteri"] = zaman["musteri_norm"].map(canonical_map).fillna(zaman["musteri_norm"])

evrak = evrak[evrak["musteri"] != ""]
zaman = zaman[zaman["musteri"] != ""]

# Aggregate Tablolar
evrak_agg = (
    evrak.groupby("musteri")
    .agg(toplam=("evrak_var", "size"), var_sayisi=("evrak_var", "sum"))
    .reset_index()
)
evrak_agg["yok_sayisi"] = evrak_agg["toplam"] - evrak_agg["var_sayisi"]
evrak_agg["evrak_basari_%"] = evrak_agg.apply(lambda r: pct(r["var_sayisi"], r["toplam"]), axis=1)

zaman_pivot = zaman.groupby(["musteri", "zaman_kategori"]).size().unstack(fill_value=0)
for cat in ["Geç", "Zamanında", "Erken"]:
    if cat not in zaman_pivot.columns:
        zaman_pivot[cat] = 0
zaman_pivot = zaman_pivot.reset_index()
zaman_pivot["degerlendirilen"] = zaman_pivot["Geç"] + zaman_pivot["Zamanında"] + zaman_pivot["Erken"]
zaman_pivot["zaman_basari_%"] = zaman_pivot.apply(
    lambda r: pct(r["Zamanında"] + r["Erken"], r["degerlendirilen"]), axis=1
)

# ========================================================================================
# MOD 1: MÜŞTERİ ANALİZİ (GÖRSELLEŞTİRME & OTOMATİK YORUM)
# ========================================================================================
if mode == "👤 Müşteri Analizi":
    tum_musteriler = sorted(set(evrak["musteri"]) | set(zaman["musteri"]))
    secilen = st.selectbox("Müşteri Seçin:", tum_musteriler)

    m_evrak = evrak[evrak["musteri"] == secilen]
    m_zaman = zaman[zaman["musteri"] == secilen]

    toplam_evrak = len(m_evrak)
    var_sayisi = int(m_evrak["evrak_var"].sum())
    yok_sayisi = toplam_evrak - var_sayisi
    evrak_oran = pct(var_sayisi, toplam_evrak)

    zaman_dagilim = m_zaman["zaman_kategori"].value_counts().to_dict()
    degerlendirilen = zaman_dagilim.get("Geç", 0) + zaman_dagilim.get("Zamanında", 0) + zaman_dagilim.get("Erken", 0)
    zaman_oran = pct(zaman_dagilim.get("Zamanında", 0) + zaman_dagilim.get("Erken", 0), degerlendirilen)

    col1, col2 = st.columns(2)
    with col1:
        if toplam_evrak > 0:
            fig1 = px.pie(
                names=["Evrakı Var", "Evrakı Yok"],
                values=[var_sayisi, yok_sayisi],
                title=f"{secilen} - Evrak Durumu",
                color=["Evrakı Var", "Evrakı Yok"],
                color_discrete_map={"Evrakı Var": "#2ecc71", "Evrakı Yok": "#e74c3c"},
                hole=0.4
            )
            st.plotly_chart(fig1, use_container_width=True)
        else:
            st.warning("Bu müşteri için evrak kaydı bulunamadı.")

    with col2:
        if zaman_dagilim:
            renk_map = {"Geç": "#e74c3c", "Zamanında": "#3498db", "Erken": "#2ecc71"}
            fig2 = px.pie(
                names=list(zaman_dagilim.keys()),
                values=list(zaman_dagilim.values()),
                title=f"{secilen} - Teslimat Zamanlaması",
                color=list(zaman_dagilim.keys()),
                color_discrete_map=renk_map,
                hole=0.4
            )
            st.plotly_chart(fig2, use_container_width=True)
        else:
            st.warning("Bu müşteri için zamanlama kaydı bulunamadı.")

    st.subheader("💡 Müşteri Otomatik Analiz Yorumu")
    st.info(generate_commentary(secilen, evrak_oran, toplam_evrak, yok_sayisi, zaman_oran, zaman_dagilim))

# ========================================================================================
# MOD 2: EVRAK BAŞARI SIRALAMASI
# ========================================================================================
elif mode == "📄 Evrak Başarı Sıralaması":
    st.subheader("Müşterilere Göre Evrak Başarısı")
    siralama = st.radio("Sıralama Yönü", ["Çoktan Aza", "Azdan Çoka"], horizontal=True)

    tablo = evrak_agg.copy()
    tablo = tablo.sort_values("evrak_basari_%", ascending=(siralama == "Azdan Çoka"))

    fig = px.bar(
        tablo, x="evrak_basari_%", y="musteri", orientation="h",
        title="Evrak Başarı Oranı (%)", color="evrak_basari_%",
        color_continuous_scale=["#e74c3c", "#f1c40f", "#2ecc71"],
        text_auto=".1f"
    )
    st.plotly_chart(fig, use_container_width=True)
    st.dataframe(tablo, use_container_width=True)

# ========================================================================================
# MOD 3: ZAMAN BAŞARI SIRALAMASI
# ========================================================================================
elif mode == "⏱️ Zaman Başarı Sıralaması":
    st.subheader("Müşterilere Göre Zaman Başarısı")
    siralama = st.radio("Sıralama Yönü", ["Çoktan Aza", "Azdan Çoka"], horizontal=True)

    tablo = zaman_pivot.copy()
    tablo = tablo.sort_values("zaman_basari_%", ascending=(siralama == "Azdan Çoka"))

    fig = px.bar(
        tablo, x="zaman_basari_%", y="musteri", orientation="h",
        title="Zamanında + Erken Teslimat Oranı (%)", color="zaman_basari_%",
        color_continuous_scale=["#e74c3c", "#f1c40f", "#2ecc71"],
        text_auto=".1f"
    )
    st.plotly_chart(fig, use_container_width=True)
    st.dataframe(tablo, use_container_width=True)
