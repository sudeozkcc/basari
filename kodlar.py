import re
from difflib import SequenceMatcher

import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(page_title="Teslimat Performans Analizi", page_icon="📦", layout="wide")

# --------------------------------------------------------------------------------------
# YARDIMCI FONKSİYONLAR
# --------------------------------------------------------------------------------------

def find_col(df: pd.DataFrame, target: str):
    """Sütun adını, olası baş/son boşluk ve büyük/küçük harf farklarına bakmadan bulur."""
    target_clean = target.strip().lower()
    for col in df.columns:
        if str(col).strip().lower() == target_clean:
            return col
    # kısmi eşleşme (örn. 'Siparişi Veren Müş.' -> 'Siparişi Veren Müşterisi')
    for col in df.columns:
        if target_clean in str(col).strip().lower():
            return col
    return None


def normalize_name(name) -> str:
    """Müşteri ismini karşılaştırmaya uygun hale getirir."""
    if pd.isna(name):
        return ""
    s = str(name).strip()
    s = s.replace("İ", "I").replace("ı", "i").upper()
    s = re.sub(r"[.,;:]", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


@st.cache_data(show_spinner=False)
def build_canonical_map(all_names: list, threshold: float = 0.88) -> dict:
    """Birbirine çok benzeyen (yazım farkı olan) müşteri isimlerini tek bir isim altında birleştirir."""
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
        rep = max(cluster, key=len)  # en uzun / en detaylı yazımı temsilci seç
        for n in cluster:
            mapping[n] = rep
    return mapping


@st.cache_data(show_spinner=False)
def load_excel(file) -> pd.DataFrame:
    return pd.read_excel(file)


def pct(a, b):
    return round((a / b) * 100, 2) if b else 0.0


# --------------------------------------------------------------------------------------
# VERİ HAZIRLAMA
# --------------------------------------------------------------------------------------

def prepare_evrak_df(df: pd.DataFrame):
    col_musteri = find_col(df, "Siparişi Veren Müş.")
    col_durum = find_col(df, "Teslim Evrak Durum")
    col_siparis_no = find_col(df, "Sipariş No")
    col_lojistik = find_col(df, "Lojistik Birim Adı")
    col_yon = find_col(df, "Yön. Tipi")
    col_tarih = find_col(df, "Oluşturma Tarihi")

    missing = [n for n, c in [("Siparişi Veren Müş.", col_musteri), ("Teslim Evrak Durum", col_durum)] if c is None]
    if missing:
        st.error(f"Evrak dosyasında şu sütunlar bulunamadı: {', '.join(missing)}. "
                 f"Dosyadaki sütunlar: {list(df.columns)}")
        st.stop()

    out = pd.DataFrame()
    out["musteri_ham"] = df[col_musteri]
    out["musteri_norm"] = out["musteri_ham"].apply(normalize_name)
    out["evrak_durum"] = df[col_durum].astype(str).str.strip().str.upper()
    out["evrak_var"] = out["evrak_durum"].str.contains("VAR", na=False)
    out["siparis_no"] = df[col_siparis_no] if col_siparis_no else None
    out["lojistik_birim"] = df[col_lojistik] if col_lojistik else None
    out["yon_tipi"] = df[col_yon] if col_yon else None
    if col_tarih:
        out["tarih"] = pd.to_datetime(df[col_tarih], errors="coerce")
    return out


def prepare_zaman_df(df: pd.DataFrame):
    col_musteri = find_col(df, "Siparişi Veren Müş.")
    col_durum = find_col(df, "Durum")
    col_il = find_col(df, "Tes. İl")
    col_ilce = find_col(df, "Tes. İlçe")
    col_beklenen = find_col(df, "Beklenen Teslim Tarihi")
    col_irs = find_col(df, "İrs No")

    missing = [n for n, c in [("Siparişi Veren Müş.", col_musteri), ("Durum", col_durum)] if c is None]
    if missing:
        st.error(f"Zamanlama dosyasında şu sütunlar bulunamadı: {', '.join(missing)}. "
                 f"Dosyadaki sütunlar: {list(df.columns)}")
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
        if "BEKLE" in d:
            return "Teslimat Bekleniyor"
        return "Diğer"

    out["zaman_kategori"] = durum_norm.apply(kategori)
    out["il"] = df[col_il] if col_il else None
    out["ilce"] = df[col_ilce] if col_ilce else None
    out["irs_no"] = df[col_irs] if col_irs else None
    if col_beklenen:
        out["beklenen_tarih"] = pd.to_datetime(df[col_beklenen], errors="coerce")
    return out


# --------------------------------------------------------------------------------------
# YORUM ÜRETİMİ
# --------------------------------------------------------------------------------------

def generate_commentary(musteri, evrak_oran, evrak_toplam, evrak_yok, zaman_oran, zaman_dagilim, en_sorunlu_birim=None, en_sorunlu_yon=None):
    lines = []

    if evrak_toplam > 0:
        if evrak_oran >= 95:
            seviye = "çok iyi"
        elif evrak_oran >= 85:
            seviye = "iyi"
        elif evrak_oran >= 70:
            seviye = "orta düzeyde, iyileştirmeye açık"
        else:
            seviye = "zayıf, acil aksiyon gerektiriyor"
        lines.append(f"**Evrak performansı:** {musteri}, %{evrak_oran} evrak başarı oranıyla **{seviye}** durumda "
                      f"({evrak_toplam} siparişin {evrak_yok} tanesinde teslim evrakı eksik).")
        if en_sorunlu_birim:
            lines.append(f"Evrak eksikliği en çok **{en_sorunlu_birim}** üzerinden yaşanıyor; süreç bu noktada gözden geçirilebilir.")
        if en_sorunlu_yon:
            lines.append(f"Evrak eksik siparişlerin çoğu **{en_sorunlu_yon}** yönlendirme tipinde gerçekleşmiş.")
    else:
        lines.append("Bu müşteri için evrak dosyasında veri bulunamadı.")

    toplam_zaman = sum(zaman_dagilim.values())
    if toplam_zaman > 0:
        gec_oran = pct(zaman_dagilim.get("Geç", 0), toplam_zaman)
        if zaman_oran >= 90:
            zseviye = "çok iyi"
        elif zaman_oran >= 75:
            zseviye = "iyi"
        elif zaman_oran >= 60:
            zseviye = "orta düzeyde"
        else:
            zseviye = "zayıf"
        lines.append(f"**Zaman performansı:** Zamanında + erken teslim oranı %{zaman_oran} ile **{zseviye}**. "
                      f"Siparişlerin %{gec_oran}'i geç teslim edilmiş.")
        if gec_oran > 25:
            lines.append("⚠️ Geç teslim oranı yüksek; rota planlaması veya depo çıkış süreçleri incelenmeli.")
    else:
        lines.append("Bu müşteri için zamanlama dosyasında veri bulunamadı.")

    return "\n\n".join(lines)


# --------------------------------------------------------------------------------------
# ARAYÜZ
# --------------------------------------------------------------------------------------

st.title("📦 Teslimat Performans Analiz Paneli")
st.caption("Evrak durumu ve teslimat zamanlaması verilerini müşteri bazında görselleştirin.")

with st.sidebar:
    st.header("1️⃣ Dosyaları Yükle")
    file_evrak = st.file_uploader("Evrak Durumu Excel dosyası", type=["xlsx", "xls"], key="evrak")
    file_zaman = st.file_uploader("Zamanlama Excel dosyası", type=["xlsx", "xls"], key="zaman")

    st.header("2️⃣ Mod Seç")
    mode = st.radio(
        "Görüntüleme modu",
        ["👤 Müşteri Analizi", "📄 Evrak Başarı Sıralaması", "⏱️ Zaman Başarı Sıralaması"],
    )

if not file_evrak or not file_zaman:
    st.info("Devam etmek için lütfen soldaki menüden her iki Excel dosyasını da yükleyin.")
    st.stop()

df_evrak_raw = load_excel(file_evrak)
df_zaman_raw = load_excel(file_zaman)

evrak = prepare_evrak_df(df_evrak_raw)
zaman = prepare_zaman_df(df_zaman_raw)

# Müşteri isimlerini iki dosya arasında eşleştir (yazım farklarını tolere ederek)
all_norm_names = list(evrak["musteri_norm"]) + list(zaman["musteri_norm"])
canonical_map = build_canonical_map(all_norm_names, threshold=0.88)

evrak["musteri"] = evrak["musteri_norm"].map(canonical_map).fillna(evrak["musteri_norm"])
zaman["musteri"] = zaman["musteri_norm"].map(canonical_map).fillna(zaman["musteri_norm"])

evrak = evrak[evrak["musteri"] != ""]
zaman = zaman[zaman["musteri"] != ""]

# --------------------------------------------------------------------------------------
# Aggregate tablolar
# --------------------------------------------------------------------------------------

evrak_agg = (
    evrak.groupby("musteri")
    .agg(toplam=("evrak_var", "size"), var_sayisi=("evrak_var", "sum"))
    .reset_index()
)
evrak_agg["yok_sayisi"] = evrak_agg["toplam"] - evrak_agg["var_sayisi"]
evrak_agg["evrak_basari_%"] = evrak_agg.apply(lambda r: pct(r["var_sayisi"], r["toplam"]), axis=1)

zaman_pivot = zaman.groupby(["musteri", "zaman_kategori"]).size().unstack(fill_value=0)
for cat in ["Geç", "Zamanında", "Erken", "Teslimat Bekleniyor"]:
    if cat not in zaman_pivot.columns:
        zaman_pivot[cat] = 0
zaman_pivot = zaman_pivot.reset_index()
zaman_pivot["degerlendirilen"] = zaman_pivot["Geç"] + zaman_pivot["Zamanında"] + zaman_pivot["Erken"]
zaman_pivot["zaman_basari_%"] = zaman_pivot.apply(
    lambda r: pct(r["Zamanında"] + r["Erken"], r["degerlendirilen"]), axis=1
)

# ========================================================================================
# MOD 1: MÜŞTERİ ANALİZİ
# ========================================================================================
if mode == "👤 Müşteri Analizi":
    tum_musteriler = sorted(set(evrak["musteri"]) | set(zaman["musteri"]))
    secilen = st.selectbox("Müşteri seçin", tum_musteriler)

    m_evrak = evrak[evrak["musteri"] == secilen]
    m_zaman = zaman[zaman["musteri"] == secilen]

    toplam_evrak = len(m_evrak)
    var_sayisi = int(m_evrak["evrak_var"].sum())
    yok_sayisi = toplam_evrak - var_sayisi
    evrak_oran = pct(var_sayisi, toplam_evrak)

    zaman_dagilim = m_zaman["zaman_kategori"].value_counts().to_dict()
    degerlendirilen = zaman_dagilim.get("Geç", 0) + zaman_dagilim.get("Zamanında", 0) + zaman_dagilim.get("Erken", 0)
    zaman_oran = pct(zaman_dagilim.get("Zamanında", 0) + zaman_dagilim.get("Erken", 0), degerlendirilen)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Toplam Sipariş (Evrak)", toplam_evrak)
    c2.metric("Evrak Başarı Oranı", f"%{evrak_oran}")
    c3.metric("Değerlendirilen Teslimat", degerlendirilen)
    c4.metric("Zaman Başarı Oranı", f"%{zaman_oran}")

    col1, col2 = st.columns(2)
    with col1:
        if toplam_evrak > 0:
            fig1 = px.pie(
                names=["Evrakı Var", "Evrakı Yok"],
                values=[var_sayisi, yok_sayisi],
                title="Evrak Durumu Dağılımı",
                color=["Evrakı Var", "Evrakı Yok"],
                color_discrete_map={"Evrakı Var": "#2ecc71", "Evrakı Yok": "#e74c3c"},
            )
            st.plotly_chart(fig1, use_container_width=True)
        else:
            st.warning("Bu müşteri için evrak verisi bulunamadı.")

    with col2:
        if zaman_dagilim:
            renk_map = {"Geç": "#e74c3c", "Zamanında": "#3498db", "Erken": "#2ecc71", "Teslimat Bekleniyor": "#f39c12"}
            fig2 = px.pie(
                names=list(zaman_dagilim.keys()),
                values=list(zaman_dagilim.values()),
                title="Teslimat Zamanlaması Dağılımı",
                color=list(zaman_dagilim.keys()),
                color_discrete_map=renk_map,
            )
            st.plotly_chart(fig2, use_container_width=True)
        else:
            st.warning("Bu müşteri için zamanlama verisi bulunamadı.")

    # Zaman içinde sipariş trendi (varsa)
    if "tarih" in m_evrak.columns and m_evrak["tarih"].notna().any():
        trend = m_evrak.dropna(subset=["tarih"]).copy()
        trend["gun"] = trend["tarih"].dt.date
        trend_agg = trend.groupby("gun").agg(toplam=("evrak_var", "size"), var=("evrak_var", "sum")).reset_index()
        trend_agg["oran_%"] = trend_agg.apply(lambda r: pct(r["var"], r["toplam"]), axis=1)
        fig3 = px.line(trend_agg, x="gun", y="oran_%", markers=True, title="Günlük Evrak Başarı Oranı Trendi (%)")
        st.plotly_chart(fig3, use_container_width=True)

    # En sorunlu lojistik birim / yön tipi
    en_sorunlu_birim = None
    if "lojistik_birim" in m_evrak.columns and m_evrak["lojistik_birim"].notna().any():
        eksikler = m_evrak[~m_evrak["evrak_var"]]
        if len(eksikler) > 0:
            en_sorunlu_birim = eksikler["lojistik_birim"].value_counts().idxmax()

    en_sorunlu_yon = None
    if "yon_tipi" in m_evrak.columns and m_evrak["yon_tipi"].notna().any():
        eksikler = m_evrak[~m_evrak["evrak_var"]]
        if len(eksikler) > 0:
            en_sorunlu_yon = eksikler["yon_tipi"].value_counts().idxmax()

    st.subheader("🧠 Otomatik Değerlendirme")
    st.markdown(
        generate_commentary(
            secilen, evrak_oran, toplam_evrak, yok_sayisi, zaman_oran, zaman_dagilim,
            en_sorunlu_birim, en_sorunlu_yon,
        )
    )

    with st.expander("Ham veriyi görüntüle"):
        st.write("Evrak verisi")
        st.dataframe(m_evrak.drop(columns=["musteri_norm"], errors="ignore"))
        st.write("Zamanlama verisi")
        st.dataframe(m_zaman.drop(columns=["musteri_norm"], errors="ignore"))

# ========================================================================================
# MOD 2: EVRAK BAŞARI SIRALAMASI
# ========================================================================================
elif mode == "📄 Evrak Başarı Sıralaması":
    st.subheader("Müşterilere Göre Evrak Başarı Sıralaması")
    siralama = st.radio("Sıralama yönü", ["Çoktan Aza", "Azdan Çoka"], horizontal=True)
    min_siparis = st.slider("Minimum sipariş sayısı filtresi", 1, int(evrak_agg["toplam"].max() or 1), 1)

    tablo = evrak_agg[evrak_agg["toplam"] >= min_siparis].copy()
    tablo = tablo.sort_values("evrak_basari_%", ascending=(siralama == "Azdan Çoka"))

    fig = px.bar(
        tablo, x="evrak_basari_%", y="musteri", orientation="h",
        title="Evrak Başarı Oranı (%)", color="evrak_basari_%",
        color_continuous_scale=["#e74c3c", "#f1c40f", "#2ecc71"],
        height=max(400, 28 * len(tablo)),
    )
    fig.update_layout(yaxis=dict(categoryorder="total ascending" if siralama == "Çoktan Aza" else "total descending"))
    st.plotly_chart(fig, use_container_width=True)

    st.dataframe(
        tablo.rename(columns={
            "musteri": "Müşteri", "toplam": "Toplam Sipariş",
            "var_sayisi": "Evrakı Var", "yok_sayisi": "Evrakı Yok", "evrak_basari_%": "Başarı %",
        }),
        use_container_width=True, hide_index=True,
    )

# ========================================================================================
# MOD 3: ZAMAN BAŞARI SIRALAMASI
# ========================================================================================
elif mode == "⏱️ Zaman Başarı Sıralaması":
    st.subheader("Müşterilere Göre Zaman Başarı Sıralaması")
    siralama = st.radio("Sıralama yönü", ["Çoktan Aza", "Azdan Çoka"], horizontal=True)
    min_teslimat = st.slider(
        "Minimum değerlendirilen teslimat filtresi", 1, int(zaman_pivot["degerlendirilen"].max() or 1), 1
    )

    tablo = zaman_pivot[zaman_pivot["degerlendirilen"] >= min_teslimat].copy()
    tablo = tablo.sort_values("zaman_basari_%", ascending=(siralama == "Azdan Çoka"))

    fig = px.bar(
        tablo, x="zaman_basari_%", y="musteri", orientation="h",
        title="Zamanında + Erken Teslim Oranı (%)", color="zaman_basari_%",
        color_continuous_scale=["#e74c3c", "#f1c40f", "#2ecc71"],
        height=max(400, 28 * len(tablo)),
    )
    st.plotly_chart(fig, use_container_width=True)

    st.dataframe(
        tablo[["musteri", "Geç", "Zamanında", "Erken", "Teslimat Bekleniyor", "degerlendirilen", "zaman_basari_%"]]
        .rename(columns={
            "musteri": "Müşteri", "degerlendirilen": "Değerlendirilen Teslimat", "zaman_basari_%": "Başarı %",
        }),
        use_container_width=True, hide_index=True,
    )
