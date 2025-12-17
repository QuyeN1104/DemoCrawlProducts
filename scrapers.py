import time
import requests
import concurrent.futures
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager


# --- CLASS CHA (BASE) ---
class BaseScraper:
    def __init__(self):
        self.session = requests.Session()
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept-Language': 'vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7'
        }
        self.session.headers.update(self.headers)

    def _setup_driver(self):
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--window-size=1920,1080")
        prefs = {"profile.managed_default_content_settings.images": 2}
        chrome_options.add_experimental_option("prefs", prefs)

        try:
            return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
        except Exception:
            return webdriver.Chrome(options=chrome_options)

    def get_links(self, url, item_selector, link_selector=None, progress_callback=None):
        """Mặc định: Dùng Scroll (Cho Viglacera Tiles)"""
        driver = None
        product_links = []
        try:
            if progress_callback: progress_callback(f"🚀 Đang khởi động trình duyệt...")
            driver = self._setup_driver()

            if progress_callback: progress_callback(f"🔗 Đang truy cập: {url}")
            driver.get(url)
            time.sleep(3)

            if progress_callback: progress_callback("🔄 Đang cuộn trang (Lazy Load)...")
            last_height = driver.execute_script("return document.body.scrollHeight")

            while True:
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(1.5)
                new_height = driver.execute_script("return document.body.scrollHeight")
                if new_height == last_height:
                    break
                last_height = new_height

            soup = BeautifulSoup(driver.page_source, 'html.parser')
            items = soup.select(item_selector)

            if progress_callback: progress_callback(f"✅ Tìm thấy {len(items)} thẻ sản phẩm. Đang trích xuất link...")
            domain = "/".join(url.split("/")[:3])

            for item in items:
                tag = item.select_one(link_selector) if link_selector else item
                if tag and tag.get('href'):
                    href = tag.get('href')
                    if not href.startswith('http'): href = domain + href
                    product_links.append(href)
        except Exception as e:
            if progress_callback: progress_callback(f"❌ Lỗi Selenium: {e}")
            print(f"Error: {e}")
        finally:
            if driver: driver.quit()
        return list(set(product_links))

    def parse_detail(self, soup, url):
        raise NotImplementedError

    def _fetch_single_product(self, link):
        try:
            response = self.session.get(link, timeout=15)
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                return self.parse_detail(soup, link)
        except Exception as e:
            print(f"Lỗi link {link}: {e}")
        return None

    def scrape_details_list(self, links, progress_bar=None, status_text=None):
        data = []
        total = len(links)
        MAX_WORKERS = 10
        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            future_to_url = {executor.submit(self._fetch_single_product, link): link for link in links}
            completed = 0
            for future in concurrent.futures.as_completed(future_to_url):
                result = future.result()
                if result: data.append(result)
                completed += 1
                if progress_bar: progress_bar.progress(completed / total)
                if status_text: status_text.text(f"Đã tải xong: {completed}/{total} sản phẩm")
        return data


# --- CLASS 1: Viglacera Tiles ---
class ViglaceraTilesScraper(BaseScraper):
    def parse_detail(self, soup, url):
        code_tag = soup.select_one('.title-main h2 strong')
        product_code = code_tag.text.strip() if code_tag else "N/A"
        breadcrumb = soup.select_one('.breadcrumb li:last-child a')
        collection = breadcrumb.text.strip() if breadcrumb else "N/A"
        images = []
        for img in soup.select('.detail-pic img'):
            src = img.get('src')
            if src:
                if not src.startswith('http'): src = "https://viglaceratiles.vn" + src
                images.append(src)
        dynamic_specs = {}
        for item in soup.select('.des-item'):
            key_tag = item.select_one('span')
            val_tag = item.select_one('h3')
            if key_tag and val_tag: dynamic_specs[key_tag.text.strip().title()] = val_tag.text.strip()
        final_data = {
            'URL': url, 'Mã Sản Phẩm': product_code, 'Bộ Sưu Tập': collection,
            'Ảnh Đại Diện': images[0] if images else "N/A", 'Danh Sách Ảnh': images
        }
        final_data.update(dynamic_specs)
        return final_data


# --- CLASS 2: Viglacera AAC ---
class ViglaceraAACScraper(BaseScraper):
    def parse_detail(self, soup, url):
        name_tag = soup.find('h1', itemprop='name')
        product_name = name_tag.text.strip() if name_tag else "N/A"
        brand_tag = soup.select_one('.pro-brand a')
        brand = brand_tag.text.strip() if brand_tag else "N/A"
        type_tag = soup.select_one('.pro-type a')
        product_type = type_tag.text.strip() if type_tag else "N/A"
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
        specs = {}
        table = soup.find('table')
        if table:
            for row in table.find_all('tr'):
                cols = row.find_all(['td', 'th'])
                row_data = [c.text.strip() for c in cols if c.text.strip()]
                if not row_data: continue
                if any(x in row_data[0].lower() for x in ['chỉ tiêu', 'thông số', 'đơn vị']): continue
                if len(row_data) >= 2:
                    key = row_data[0]
                    value = row_data[-1]
                    if len(row_data) > 2: key = f"{key} ({' '.join(row_data[1:-1])})"
                    specs[key] = value
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
            'URL': url, 'Tên Sản Phẩm': product_name, 'Thương Hiệu': brand,
            'Loại Sản Phẩm': product_type, 'Ảnh Đại Diện': images[0] if images else "N/A", 'Danh Sách Ảnh': images
        }
        final_data.update(info_dict)
        final_data.update(specs)
        return final_data


# --- CLASS 3: VTHM Group (Logic Data-Driven) ---
class VthmGroupScraper(BaseScraper):

    def get_links(self, url, item_selector, link_selector=None, progress_callback=None):
        driver = None
        product_links = set()  # Sử dụng SET để tự động loại bỏ link trùng

        # Selector chỉ dùng để TÌM nút, không dùng để check disabled nữa
        NEXT_BUTTON_SELECTOR = "nav.pagination button.btn-next"

        try:
            if progress_callback: progress_callback(f"🚀 Đang khởi động trình duyệt...")
            driver = self._setup_driver()

            if progress_callback: progress_callback(f"🔗 Đang truy cập: {url}")
            driver.get(url)
            time.sleep(5)

            page_count = 1
            page_des = 20
            last_first_link = ""  # Biến để kiểm tra trang đã load xong chưa

            while True:
                # --- BƯỚC 1: LẤY DỮ LIỆU ---
                # Chờ tối đa 10s cho đến khi link sản phẩm đầu tiên thay đổi so với trang trước
                retries = 0
                items = []
                while retries < 10:
                    soup = BeautifulSoup(driver.page_source, 'html.parser')
                    items = soup.select(item_selector)

                    if not items: break
                    current_first_link = items[0].get('href')

                    # Nếu là trang 1 HOẶC link đầu tiên đã khác trang trước -> OK, trang mới đã load
                    if page_count == 1 or current_first_link != last_first_link:
                        last_first_link = current_first_link
                        break

                    time.sleep(1)
                    retries += 1

                # Lấy link từ các item tìm được
                current_page_new_links = 0
                for item in items:
                    href = item.get('href')
                    if href:
                        if not href.startswith('http'): href = "https://vthmgroup.vn" + href

                        # --- LOGIC QUAN TRỌNG NHẤT Ở ĐÂY ---
                        if href not in product_links:
                            product_links.add(href)
                            current_page_new_links += 1

                # In thông tin
                total_collected = len(product_links)
                msg = f"📄 Trang {page_count}: Thêm {current_page_new_links} sản phẩm mới. Tổng: {total_collected}"
                print(msg)
                if progress_callback: progress_callback(msg)

                # --- BƯỚC 2: KIỂM TRA ĐIỀU KIỆN DỪNG (LOGIC TỔNG SẢN PHẨM) ---
                # Nếu bấm chuyển trang rồi mà không lấy thêm được link nào mới -> ĐÃ HẾT
                if page_count == page_des:
                    break


                if current_page_new_links == 0 and page_count > 1:
                    print("🛑 Không có sản phẩm mới -> Đã đến trang cuối.")
                    break

                # --- BƯỚC 3: BẤM NÚT NEXT ---
                try:
                    next_btn = driver.find_element(By.CSS_SELECTOR, NEXT_BUTTON_SELECTOR)

                    # Cuộn tới nút và click
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", next_btn)
                    time.sleep(1)
                    driver.execute_script("arguments[0].click();", next_btn)

                    print(f"⏳ Đang tải trang {page_count + 1}...")
                    page_count += 1

                    # Chờ 1 chút sau khi click để web bắt đầu request
                    time.sleep(2)

                except Exception:
                    print(f"🛑 Không tìm thấy nút Next (Hoặc nút đã bị ẩn) -> Dừng.")
                    break

        except Exception as e:
            if progress_callback: progress_callback(f"❌ Lỗi Selenium: {e}")
            print(f"Error: {e}")
        finally:
            if driver: driver.quit()

        return list(product_links)

    def parse_detail(self, soup, url):
        try:
            name_tag = soup.select_one('h1')
            product_name = name_tag.text.strip() if name_tag else "N/A"

            specs = {}
            # Grid items
            attr_items = soup.select('.attribute-item')
            for item in attr_items:
                lbl = item.select_one('.text-content-3')
                val = item.select_one('.text-content-1')
                if lbl and val: specs[lbl.text.strip().title()] = val.text.strip()

            # Flex items
            flex_rows = soup.select('.flex.gap-4')
            for row in flex_rows:
                lbl = row.select_one('.w-26.text-content-3')
                val = row.select_one('.text-content-1')
                if lbl and val: specs[lbl.text.strip().title()] = val.text.strip()

            images = []
            img_tags = soup.select('.slides img, .swiper-slide img, main img')
            for img in img_tags:
                src = img.get('src') or img.get('data-nuxt-img')
                if src and 'http' in src and not any(x in src.lower() for x in ['logo', 'icon', '.svg']):
                    q_index = src.find('?')
                    src = src[:q_index]
                    images.append(src)
            clean_images = list(set(images))

            final_data = {
                'URL': url, 'Mã Sản Phẩm': product_name,
                'Thương Hiệu': specs.get('Thương Hiệu', 'N/A'), 'Kích Thước': specs.get('Kích Thước', 'N/A'),
                'Bề Mặt': specs.get('Bề Mặt', 'N/A'), 'Xương Gạch': specs.get('Xương', 'N/A'),
                 'Danh Sách Ảnh': clean_images
            }
            for k, v in specs.items():
                if k not in final_data: final_data[k] = v

            return final_data
        except Exception as e:
            print(f"Lỗi parse: {e}")
            return None


# --- CLASS 4: TaiceraVN (Đã tối ưu lấy chi tiết từ thẻ P) ---
# --- CLASS 4: TaiceraVN (Bản nâng cấp: Smart Wait + Scroll) ---
class TaiceraScraper(BaseScraper):

    def get_links(self, url, item_selector, link_selector=None, progress_callback=None):
        driver = None
        product_links = set()

        # Selector nút Next
        NEXT_BTN_XPATH = "//ul[contains(@class,'page-numbers')]//li/a[contains(@class,'next')]"

        try:
            if progress_callback: progress_callback(f"🚀 Đang khởi động trình duyệt...")
            driver = self._setup_driver()
            wait = WebDriverWait(driver, 15)  # Thời gian chờ tối đa 15s

            # --- BƯỚC 1: QUÉT DANH MỤC ---
            target_urls = []
            is_general_page = "san-pham" in url or len(url.split('/')) < 5

            if is_general_page:
                if progress_callback: progress_callback(f"🔍 Đang quét menu tìm danh mục...")
                driver.get(url)
                time.sleep(3)
                soup = BeautifulSoup(driver.page_source, 'html.parser')

                menu_links = soup.select('#menu-item-1665 .sub-menu a')
                for a in menu_links:
                    href = a.get('href')
                    if href and 'http' in href: target_urls.append(href)

                if not target_urls:
                    see_more = soup.select('h3.section-title a')
                    for a in see_more:
                        href = a.get('href')
                        if href: target_urls.append(href)

                target_urls = list(set(target_urls))
                if progress_callback: progress_callback(f"✅ Tìm thấy {len(target_urls)} danh mục. Bắt đầu cào.")
            else:
                target_urls.append(url)

            # --- BƯỚC 2: CÀO CHI TIẾT ---
            total_cats = len(target_urls)
            for i, cat_url in enumerate(target_urls):
                msg = f"📂 [{i + 1}/{total_cats}] Danh mục: {cat_url}"
                print(msg)
                if progress_callback: progress_callback(msg)

                try:
                    driver.get(cat_url)
                    page_count = 1

                    while True:
                        # --- [MỚI] KỸ THUẬT CHỐNG SÓT SẢN PHẨM ---

                        # 1. Chờ sản phẩm xuất hiện (Thay vì sleep cứng)
                        try:
                            # Chờ ít nhất 1 sản phẩm xuất hiện trong DOM
                            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, item_selector)))
                        except:
                            print("   ⚠️ Không thấy sản phẩm nào (Có thể trang trống hoặc load lỗi).")
                            break  # Hết hoặc lỗi

                        # 2. Cuộn trang xuống cuối để kích hoạt Lazy Load (nếu có)
                        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                        time.sleep(2)  # Nghỉ 1 chút cho ảnh/item load lên

                        # 3. Lấy dữ liệu
                        soup = BeautifulSoup(driver.page_source, 'html.parser')
                        items = soup.select(item_selector)

                        current_links_count = 0
                        for item in items:
                            tag = item.select_one(link_selector) if link_selector else item.select_one('a')
                            href = tag.get('href') if tag else None
                            if href:
                                if not href.startswith('http'): href = "https://taiceravn.com" + href
                                if href not in product_links:
                                    product_links.add(href)
                                    current_links_count += 1

                        print(f"   ↳ Trang {page_count}: +{current_links_count} SP.")

                        # Điều kiện dừng an toàn
                        if current_links_count == 0 and page_count > 1:
                            # Thử đợi thêm 3s và quét lại lần cuối xem có phải do mạng lag không
                            time.sleep(3)
                            soup = BeautifulSoup(driver.page_source, 'html.parser')
                            items = soup.select(item_selector)
                            if not items: break

                        # 4. Chuyển trang
                        try:
                            next_btn = driver.find_element(By.XPATH, NEXT_BTN_XPATH)
                            next_href = next_btn.get_attribute('href')
                            if next_href:
                                driver.get(next_href)
                                page_count += 1
                            else:
                                break
                        except Exception:
                            break

                except Exception as e:
                    print(f"Lỗi danh mục {cat_url}: {e}")
                    continue

        except Exception as e:
            if progress_callback: progress_callback(f"❌ Lỗi Selenium: {e}")
            print(f"Error: {e}")
        finally:
            if driver: driver.quit()

        return list(product_links)

    def parse_detail(self, soup, url):
        # ... (Giữ nguyên hàm parse_detail KHÔNG ĐỔI) ...
        try:
            name_tag = soup.select_one('.product-title, h1.entry-title')
            product_name = name_tag.text.strip() if name_tag else "N/A"

            price_tag = soup.select_one('.price span.amount bdi')
            price_sale = soup.select_one('.price ins span.amount bdi')
            price = price_sale.text.strip() if price_sale else (price_tag.text.strip() if price_tag else "Liên hệ")

            images = []
            img_tags = soup.select('.product-gallery-slider img, .woocommerce-product-gallery__image img')
            for img in img_tags:
                src = img.get('src') or img.get('data-src') or img.get('data-large_image')
                if src and 'http' in src: images.append(src)
            images = list(set(images))

            specs = {}
            desc_content = soup.select_one('#tab-description, .woocommerce-Tabs-panel--description')
            if desc_content:
                paragraphs = desc_content.find_all('p')
                for p in paragraphs:
                    text = p.get_text().strip()
                    clean_text = text.lstrip('–- ').strip()
                    if ':' in clean_text:
                        parts = clean_text.split(':', 1)
                        specs[parts[0].strip().capitalize()] = parts[1].strip()
                    elif "Đơn giá" in clean_text:
                        specs["Thông tin giá"] = clean_text

            rows = soup.select('table.woocommerce-product-attributes tr')
            for row in rows:
                th = row.select_one('th')
                td = row.select_one('td')
                if th and td: specs[th.text.strip()] = td.text.strip()

            return {
                'URL': url,
                'Tên Sản Phẩm': product_name,
                'Giá': price,
                'Ảnh Đại Diện': images[0] if images else "N/A",
                'Danh Sách Ảnh': images,
                **specs
            }
        except Exception as e:
            print(f"Lỗi parse Taicera: {e}")
            return None