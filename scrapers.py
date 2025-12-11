import time
import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager


# --- CLASS CHA (CHỨA CÁC HÀM CHUNG) ---
class BaseScraper:
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept-Language': 'vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7'
        }

    def _setup_driver(self):
        """
        Khởi tạo Selenium Driver.
        Tự động xử lý cả môi trường Local (Windows/Mac) và Cloud (Linux).
        """
        chrome_options = Options()
        chrome_options.add_argument("--headless")  # Chạy ẩn. Nếu muốn xem trình duyệt chạy thì comment dòng này lại.
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--window-size=1920,1080")

        # --- ƯU TIÊN 1: Dùng webdriver-manager (Tốt nhất cho Local Windows) ---
        try:
            return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
        except Exception as e:
            print(f"⚠️ Không dùng được Webdriver Manager: {e}")

        # --- ƯU TIÊN 2: Dùng Driver mặc định của hệ thống (Tốt cho Streamlit Cloud/Linux) ---
        try:
            return webdriver.Chrome(options=chrome_options)
        except Exception as e:
            print(f"❌ Lỗi khởi tạo Driver: {e}")
            return None  # Trả về None nếu thất bại toàn tập

    def get_links(self, url, item_selector, link_selector='a.link-load', progress_callback=None):
        """Dùng Selenium cuộn trang và lấy danh sách Link."""

        driver = None  # Khai báo driver là None trước để tránh lỗi reference
        product_links = []

        try:
            if progress_callback: progress_callback(f"🚀 Đang khởi động trình duyệt...")

            # Khởi tạo driver
            driver = self._setup_driver()

            # Nếu driver khởi tạo thất bại (vẫn là None) thì ném lỗi
            if not driver:
                raise Exception("Không thể khởi động trình duyệt Chrome/Driver.")

            if progress_callback: progress_callback(f"🔗 Đang truy cập: {url}")
            driver.get(url)
            time.sleep(2)

            if progress_callback: progress_callback("🔄 Đang cuộn trang (Lazy Load)...")
            last_height = driver.execute_script("return document.body.scrollHeight")

            while True:
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
                new_height = driver.execute_script("return document.body.scrollHeight")
                if new_height == last_height:
                    break
                last_height = new_height

            # Phân tích HTML để lấy link
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            items = soup.select(item_selector)

            if progress_callback: progress_callback(f"✅ Tìm thấy {len(items)} thẻ sản phẩm. Đang lọc link...")

            domain = "/".join(url.split("/")[:3])

            for item in items[:6]:
                link_tag = item.select_one(link_selector)
                if link_tag and link_tag.get('href'):
                    full_link = link_tag.get('href')
                    if not full_link.startswith('http'):
                        full_link = domain + full_link
                    product_links.append(full_link)

        except Exception as e:
            if progress_callback: progress_callback(f"❌ Lỗi Selenium: {e}")
            print(f"Lỗi chi tiết: {e}")  # In ra terminal để debug
        finally:
            # --- SỬA LỖI TẠI ĐÂY: Chỉ quit() nếu driver tồn tại ---
            if driver:
                driver.quit()

        return list(set(product_links))

    def parse_detail(self, soup, url):
        """Hàm ảo: Class con bắt buộc phải viết lại hàm này"""
        raise NotImplementedError

    def scrape_details_list(self, links, progress_bar=None, status_text=None):
        """Dùng Requests để cào chi tiết danh sách link"""
        data = []
        total = len(links)

        for i, link in enumerate(links):
            if status_text: status_text.text(f"Đang xử lý [{i + 1}/{total}]: {link}")
            if progress_bar: progress_bar.progress((i + 1) / total)

            try:
                response = requests.get(link, headers=self.headers, timeout=10)
                if response.status_code == 200:
                    soup = BeautifulSoup(response.text, 'html.parser')
                    # Gọi hàm phân tích của Class con
                    detail = self.parse_detail(soup, link)
                    if detail:
                        data.append(detail)
            except Exception as e:
                print(f"Lỗi link {link}: {e}")

        return data


# --- CLASS CON 1: Xử lý Gạch & Ngói ---
class ViglaceraTilesScraper(BaseScraper):
    def parse_detail(self, soup, url):
        # 1. Thông tin cơ bản
        code_tag = soup.select_one('.title-main h2 strong')
        product_code = code_tag.text.strip() if code_tag else "N/A"

        breadcrumb = soup.select_one('.breadcrumb li:last-child a')
        collection = breadcrumb.text.strip() if breadcrumb else "N/A"

        # 2. Hình ảnh
        images = []
        for img in soup.select('.detail-pic img'):
            src = img.get('src')
            if src:
                if not src.startswith('http'):
                    src = "https://viglaceratiles.vn" + src
                images.append(src)

        # 3. Thông số kỹ thuật
        dynamic_specs = {}
        for item in soup.select('.des-item'):
            key_tag = item.select_one('span')
            val_tag = item.select_one('h3')
            if key_tag and val_tag:
                key = key_tag.text.strip().title()
                value = val_tag.text.strip()
                dynamic_specs[key] = value

        final_data = {
            'URL': url,
            'Mã Sản Phẩm': product_code,
            'Bộ Sưu Tập': collection,
            'Ảnh Đại Diện': images[0] if images else "N/A",
            'Danh Sách Ảnh': images
        }
        final_data.update(dynamic_specs)
        return final_data


# --- CLASS CON 2: Xử lý AAC ---
class ViglaceraAACScraper(BaseScraper):
    def parse_detail(self, soup, url):
        # 1. Thông tin cơ bản
        name_tag = soup.find('h1', itemprop='name')
        product_name = name_tag.text.strip() if name_tag else "N/A"

        brand_tag = soup.select_one('.pro-brand a')
        brand = brand_tag.text.strip() if brand_tag else "N/A"

        type_tag = soup.select_one('.pro-type a')
        product_type = type_tag.text.strip() if type_tag else "N/A"

        # 2. Hình ảnh
        images = []
        main_img = soup.select_one('#ProductPhoto img')
        if main_img and main_img.get('src'):
            src = main_img.get('src')
            if src.startswith('//'): src = 'https:' + src
            images.append(src)

        for img in soup.select('#sliderproduct img'):
            src = img.get('src')
            if src:
                if src.startswith('//'): src = 'https:' + src
                if src not in images: images.append(src)

        # 3. Bảng thông số
        specs = {}
        table = soup.find('table')
        if table:
            for row in table.find_all('tr'):
                cols = row.find_all(['td', 'th'])
                row_data = [c.text.strip() for c in cols if c.text.strip()]

                if not row_data: continue
                if any(x in row_data[0].lower() for x in ['chỉ tiêu', 'thông số', 'đơn vị']):
                    continue

                if len(row_data) >= 2:
                    key = row_data[0]
                    value = row_data[-1]
                    if len(row_data) > 2:
                        key = f"{key} ({' '.join(row_data[1:-1])})"
                    specs[key] = value

        # 4. Mô tả
        info_dict = {}
        headers = soup.find_all('h2')
        target_ul = None
        for h2 in headers:
            if any(x in h2.text.upper() for x in ["THÔNG TIN", "TÍNH NĂNG"]):
                sibling = h2.find_next_sibling(['ul', 'div'])
                if sibling:
                    target_ul = sibling.find('ul') if sibling.name == 'div' else sibling
                    if target_ul: break

        if not target_ul:
            content_div = soup.find('div', class_='pro-tabcontent')
            if content_div: target_ul = content_div.find('ul')

        if target_ul:
            for i, li in enumerate(target_ul.find_all('li')):
                text = li.text.strip()
                if ':' in text:
                    k, v = text.split(':', 1)
                    info_dict[k.strip()] = v.strip()
                else:
                    info_dict[f"Thông tin {i + 1}"] = text

        final_data = {
            'URL': url,
            'Tên Sản Phẩm': product_name,
            'Thương Hiệu': brand,
            'Loại Sản Phẩm': product_type,
            'Ảnh Đại Diện': images[0] if images else "N/A",
            'Danh Sách Ảnh': images
        }
        final_data.update(info_dict)
        final_data.update(specs)
        return final_data