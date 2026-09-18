import streamlit as st
import pandas as pd
import plotly.express as px

# Sayfa Yapılandırması
st.set_page_config(page_title="Teslimat & Evrak Analiz Paneli", layout="wide")

st.title("🚚 Teslimat ve Evrak Performans Analizi")

# Sidebar - Dosya Yükleme Alanı
st.sidebar.header("📂 Veri Dosyalarını Yükle")
file_time = st.sidebar.file_uploader("Teslimat Zamanı Dosyası (.xlsx)", type=["xlsx"])
file_doc = st.sidebar.file_uploader("Evrak Durumu Dosyası (.xlsx)", type=["xlsx"])

# Mod Seçimi
st.sidebar.header("🎯 Analiz Modu")
mode = st.sidebar.radio(
    "Bir mod seçiniz:",
    [
        "1. Müşteri Detay Analizi",
        "2. Evrak Başarısı Sıralaması",
        "3. Zaman Başarısı Sıralaması"
    ]
)

@st.cache_data
def load_and_merge_data(f_time, f_doc):
    df_time = pd.read_excel(f_time)
    df_doc = pd.read_excel(f_doc)
    
    # Sütun isimlerindeki olası boşlukları temizleyelim
    df_time.columns = df_time.columns.str.strip()
    df_doc.columns = df_doc.columns.str.strip()
    
    # İki tabloyu Müşteri İskeleti/Adı üzerinden birleştiriyoruz
    # 'Müşteri' sütun adını kendi Excel sütun adınıza göre düzenleyebilirsiniz.
    merged_df = pd.merge(df_time, df_doc, on="Müşteri", how="inner")
    return merged_df

if file_time and file_doc:
    try:
        df = load_and_merge_data(file_time, file_doc)
        
        # Beklenen sütun adları kontrolü (Örnek: 'Müşteri', 'Teslimat Durumu', 'Evrak Durumu')
        # Kendi Excel'inizdeki sütun isimlerine göre aşağıdaki değişkenleri güncelleyebilirsiniz:
        col_customer = "Müşteri"
        col_time_status = "Teslimat Durumu" # Örn: Geç, Zamanında, Erken
        col_doc_status = "Evrak Durumu"      # Örn: Var, Yok

        # ---------------------------------------------------------
        # MOD 1: MÜŞTERİ DETAY ANALİZİ
        # ---------------------------------------------------------
        if mode == "1. Müşteri Detay Analizi":
            st.header("👤 Müşteri Bazlı Performans & Grafik")
            
            customers = df[col_customer].unique()
            selected_customer = st.selectbox("Bir Müşteri Seçin:", customers)
            
            cust_df = df[df[col_customer] == selected_customer]
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.subheader("Teslimat Zamanlaması Dağılımı")
                time_counts = cust_df[col_time_status].value_counts().reset_index()
                time_counts.columns = ["Durum", "Adet"]
                
                fig_time = px.pie(
                    time_counts, 
                    names="Durum", 
                    values="Adet", 
                    hole=0.4,
                    color="Durum",
                    color_discrete_map={"Zamanında": "#2ecc71", "Erken": "#3498db", "Geç": "#e74c3c"}
                )
                st.plotly_chart(fig_time, use_container_width=True)

            with col2:
                st.subheader("Evrak Durumu Dağılımı")
                doc_counts = cust_df[col_doc_status].value_counts().reset_index()
                doc_counts.columns = ["Durum", "Adet"]
                
                fig_doc = px.pie(
                    doc_counts, 
                    names="Durum", 
                    values="Adet", 
                    hole=0.4,
                    color="Durum",
                    color_discrete_map={"Var": "#2ecc71", "Yok": "#e74c3c"}
                )
                st.plotly_chart(fig_doc, use_container_width=True)

            # Otomatik Yorum/Değerlendirme
            st.markdown("---")
            st.subheader("💡 Müşteri Değerlendirme Yorumu")
            
            total_orders = len(cust_df)
            late_orders = len(cust_df[cust_df[col_time_status] == "Geç"])
            missing_docs = len(cust_df[cust_df[col_doc_status] == "Yok"])
            
            late_rate = (late_orders / total_orders) * 100
            missing_doc_rate = (missing_docs / total_orders) * 100
            
            st.write(f"**{selected_customer}** firması için toplam **{total_orders}** adet sevkiyat kaydı incelendi:")
            
            if late_rate > 20:
                st.warning(f"⚠️ Teslimat Zamanı Uyarısı: Sevkiyatların **%{late_rate:.1f}** kadarı geç teslim edilmiş. Zamanlama performansının iyileştirilmesi gerekiyor.")
            else:
                st.success(f"✅ Teslimat Zamanı Başarılı: Zamanında ve erken teslimat oranı **%{100 - late_rate:.1f}** seviyesinde.")
                
            if missing_doc_rate > 15:
                st.error(f"❌ Evrak Eksikliği Uyarısı: Sevkiyatların **%{missing_doc_rate:.1f}** kadarında evrak 'Yok' görünüyor. Süreç takibi sıkılaştırılmalı.")
            else:
                st.success(f"✅ Evrak Tamamlama Başarılı: Evrak tamamlama başarısı **%{100 - missing_doc_rate:.1f}** seviyesinde.")

        # ---------------------------------------------------------
        # MOD 2: EVRAK BAŞARISI SIRALAMASI
        # ---------------------------------------------------------
        elif mode == "2. Evrak Başarısı Sıralaması":
            st.header("📄 Müşterilerin Evrak Başarısı Sıralaması")
            
            order_type = st.radio("Sıralama Yönü:", ["Çoktan Aza (En Başarılıdan En Düşüğe)", "Azdan Çoka (En Düşükten En Başarılıya)"], horizontal=True)
            ascending_flag = True if "Azdan Çoka" in order_type else False
            
            # Müşteri bazında 'Var' olan evrak oranını hesaplama
            doc_perf = df.groupby(col_customer)[col_doc_status].apply(lambda x: (x == "Var").mean() * 100).reset_index()
            doc_perf.columns = [col_customer, "Evrak Başarı Oranı (%)"]
            
            doc_perf = doc_perf.sort_values(by="Evrak Başarı Oranı (%)", ascending=ascending_flag)
            
            fig_doc_rank = px.bar(
                doc_perf,
                x=col_customer,
                y="Evrak Başarı Oranı (%)",
                color="Evrak Başarı Oranı (%)",
                color_continuous_scale="RdYlGn",
                text_auto=".1f",
                title="Müşteri Evrak Başarı Oranları (%)"
            )
            st.plotly_chart(fig_doc_rank, use_container_width=True)
            st.dataframe(doc_perf, use_container_width=True)

        # ---------------------------------------------------------
        # MOD 3: ZAMAN BAŞARISI SIRALAMASI
        # ---------------------------------------------------------
        elif mode == "3. Zaman Başarısı Sıralaması":
            st.header("⏱️ Müşterilerin Teslimat Zamanı Başarısı Sıralaması")
            
            order_type = st.radio("Sıralama Yönü:", ["Çoktan Aza (En Başarılıdan En Düşüğe)", "Azdan Çoka (En Düşükten En Başarılıya)"], horizontal=True)
            ascending_flag = True if "Azdan Çoka" in order_type else False
            
            # Zaman başarısı = (Zamanında + Erken) teslimatların toplam içerisindeki oranı
            time_perf = df.groupby(col_customer)[col_time_status].apply(lambda x: (x.isin(["Zamanında", "Erken"])).mean() * 100).reset_index()
            time_perf.columns = [col_customer, "Zaman Başarı Oranı (%)"]
            
            time_perf = time_perf.sort_values(by="Zaman Başarı Oranı (%)", ascending=ascending_flag)
            
            fig_time_rank = px.bar(
                time_perf,
                x=col_customer,
                y="Zaman Başarı Oranı (%)",
                color="Zaman Başarı Oranı (%)",
                color_continuous_scale="RdYlGn",
                text_auto=".1f",
                title="Müşteri Zamanında/Erken Teslimat Başarı Oranları (%)"
            )
            st.plotly_chart(fig_time_rank, use_container_width=True)
            st.dataframe(time_perf, use_container_width=True)

    except Exception as e:
        st.error(f"Veriler işlenirken bir hata oluştu. Lütfen Excel sütun isimlerinizi kontrol edin. Hata mesajı: {e}")
else:
    st.info("Lütfen analize başlamak için sol menüden her iki Excel dosyasını da yükleyin.")
