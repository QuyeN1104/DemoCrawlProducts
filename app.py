import streamlit as st
import json
# import pandas as pd  <-- Không cần dùng pandas nữa vì đã bỏ phần xem bảng
from scrapers import ViglaceraTilesScraper, ViglaceraAACScraper

# --- CẤU HÌNH ---
OPTIONS = {
    "Gạch Ốp Lát (Viglacera Tiles)": {
        "url": "https://viglaceratiles.vn/san-pham/gach-op-lat.html",
        "scraper_class": ViglaceraTilesScraper,
        "item_selector": ".product-box",
        "link_selector": "a.link-load"
    },
    "Ngói Lợp (Viglacera Tiles)": {
        "url": "https://viglaceratiles.vn/san-pham/ngoi-lop.html",
        "scraper_class": ViglaceraTilesScraper,
        "item_selector": ".product-box-tiles",
        "link_selector": "a.link-load"
    },
    "Sản Phẩm AAC (Viglacera AAC)": {
        "url": "https://viglacera-aac.vn/collections/tat-ca-san-pham",
        "scraper_class": ViglaceraAACScraper,
        "item_selector": ".product-title",
        "link_selector": "a"
    }
}

# --- GIAO DIỆN WEB ---
st.set_page_config(page_title="Viglacera Data Tool", page_icon="📥", layout="centered")

st.title("📥 Tool Tải Dữ Liệu Viglacera")
st.write("Chọn danh mục sản phẩm và nhấn nút để bắt đầu.")
st.markdown("---")

# 1. Menu chọn
option_name = st.selectbox("Chọn loại sản phẩm:", list(OPTIONS.keys()))
config = OPTIONS[option_name]

# 2. Nút chạy
if st.button("🚀 Bắt đầu lấy dữ liệu", type="primary"):

    # Khởi tạo class xử lý tương ứng
    ScraperClass = config["scraper_class"]
    bot = ScraperClass()

    # --- BƯỚC 1: LẤY LINK (Selenium) ---
    status = st.status("Đang kết nối máy chủ...", expanded=True)

    links = bot.get_links(
        url=config['url'],
        item_selector=config['item_selector'],
        link_selector=config['link_selector'],
        progress_callback=status.write
    )

    status.update(label="✅ Đã kết nối xong!", state="complete", expanded=False)

    if not links:
        st.error("⚠️ Không tìm thấy sản phẩm nào. Vui lòng thử lại sau.")
    else:
        st.success(f"Đã tìm thấy **{len(links)}** sản phẩm. Đang tải chi tiết...")

        # --- BƯỚC 2: CÀO CHI TIẾT (Requests) ---
        my_bar = st.progress(0)
        txt_status = st.empty()

        # Gọi hàm cào danh sách
        data = bot.scrape_details_list(links, progress_bar=my_bar, status_text=txt_status)

        # Dọn dẹp giao diện khi xong
        my_bar.empty()
        txt_status.empty()

        if data:
            st.balloons()
            st.success("🎉 Xử lý hoàn tất!")

            # Chuẩn bị file JSON
            json_str = json.dumps(data, ensure_ascii=False, indent=4)
            file_name_clean = option_name.split('(')[0].strip().replace(' ', '_').lower()
            file_name = f"data_{file_name_clean}.json"

            # Nút tải xuống
            st.download_button(
                label=f"📥 Tải xuống file {file_name}",
                data=json_str,
                file_name=file_name,
                mime="application/json",
                type="primary"  # Làm nổi bật nút tải
            )
        else:
            st.warning("Đã chạy xong nhưng không thu thập được dữ liệu chi tiết.")