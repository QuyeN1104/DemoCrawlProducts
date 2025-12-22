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
# --- CLASS 4: TaiceraVN (Đã thêm logic cào Slider 80x80) ---
class TaiceraScraper(BaseScraper):

    def get_links(self, url, item_selector, link_selector=None, progress_callback=None):
        driver = None
        product_links = set()

        # Selector nút Next của trang phân trang (Archive Page)
        NEXT_BTN_XPATH_ARCHIVE = "//ul[contains(@class,'page-numbers')]//li/a[contains(@class,'next')]"

        try:
            if progress_callback: progress_callback(f"🚀 Đang khởi động trình duyệt...")
            driver = self._setup_driver()
            wait = WebDriverWait(driver, 15)

            # --- GIAI ĐOẠN 1: TÌM LINK DANH MỤC (LINK CON) ---
            target_urls = []
            is_general_page = "san-pham" in url or len(url.split('/')) < 5

            if is_general_page:
                if progress_callback: progress_callback(f"🔗 Đang truy cập trang chủ sản phẩm để quét...")
                driver.get(url)
                time.sleep(3)

                # === [LOGIC MỚI] CÀO TRỰC TIẾP TỪ SLIDER TRANG CHỦ (ĐẶC BIỆT LÀ 80x80) ===
                try:
                    print("⚡ Đang kích hoạt chế độ cào Slider (Gạch 80x80)...")
                    # 1. Tìm tiêu đề "Gạch 80 x 80 cm"
                    # XPath này tìm thẻ h3 chứa text, sau đó lấy cha là .col-inner để khoanh vùng
                    slider_section_xpath = "//h3[contains(., '80 x 80') or contains(., '80x80')]/ancestor::div[contains(@class, 'col-inner')]"

                    # Kiểm tra xem có tìm thấy vùng 80x80 không
                    slider_containers = driver.find_elements(By.XPATH, slider_section_xpath)

                    if slider_containers:
                        container = slider_containers[0]  # Lấy vùng đầu tiên tìm thấy
                        if progress_callback: progress_callback(
                            f"⚡ Phát hiện Slider 80x80. Đang lấy dữ liệu trực tiếp...")

                        # Thử click Next khoảng 10 lần để load hết ảnh trong slider
                        # Vì slider này lặp lại (wrapAround: true), ta cần set để lọc trùng
                        for _ in range(10):
                            # Lấy link hiện tại trong vùng này
                            soup_slider = BeautifulSoup(container.get_attribute('outerHTML'), 'html.parser')
                            links_in_slider = soup_slider.select("div.product-small a.woocommerce-LoopProduct-link")

                            count_new = 0
                            for a in links_in_slider:
                                href = a.get('href')
                                if href:
                                    if not href.startswith('http'): href = "https://taiceravn.com" + href
                                    if href not in product_links:
                                        product_links.add(href)
                                        count_new += 1

                            print(f"   -> Slider 80x80: Lấy {count_new} link mới.")

                            # Tìm nút Next TRONG VÙNG NÀY (quan trọng)
                            try:
                                # Dùng dấu chấm .// để chỉ tìm con của container
                                next_btn_slider = container.find_element(By.XPATH,
                                                                         ".//button[contains(@class, 'next')]")
                                driver.execute_script("arguments[0].click();", next_btn_slider)
                                time.sleep(1.5)  # Chờ slider trượt
                            except Exception as e:
                                print("   -> Không bấm được nút Next slider (hoặc hết):", e)
                                break
                    else:
                        print("⚠️ Không tìm thấy mục Gạch 80x80 trên trang chủ.")

                except Exception as e:
                    print(f"⚠️ Lỗi khi xử lý Slider: {e}")

                # === [HẾT LOGIC MỚI] TIẾP TỤC QUÉT DANH MỤC KHÁC ===

                soup = BeautifulSoup(driver.page_source, 'html.parser')

                # Tìm trong Menu chính
                menu_links = soup.select('#menu-item-1665 .sub-menu a')
                for a in menu_links:
                    href = a.get('href')
                    if href and 'http' in href: target_urls.append(href)

                # Tìm các nút "XEM THÊM"
                see_more_links = soup.select('h3.section-title a')
                for a in see_more_links:
                    href = a.get('href')
                    if href and 'http' in href: target_urls.append(href)

                target_urls = list(set(target_urls))

                # Loại bỏ link 80x80 khỏi danh sách quét chi tiết (vì trang đó bị lỗi như bạn nói)
                # Hoặc cứ để nó chạy, nếu lỗi thì try/except bên dưới sẽ bỏ qua
                if progress_callback: progress_callback(
                    f"✅ Đã quét xong trang chủ. Tìm thấy {len(product_links)} sp từ slider và {len(target_urls)} danh mục.")
            else:
                target_urls.append(url)

            # --- GIAI ĐOẠN 2: DUYỆT CÁC DANH MỤC CÒN LẠI ---
            total_cats = len(target_urls)
            for i, cat_url in enumerate(target_urls):
                # Nếu bạn muốn bỏ qua trang 80x80 bị lỗi để tiết kiệm thời gian
                if "80x80" in cat_url and len(product_links) > 0:
                    print(f"⏩ Bỏ qua danh mục 80x80 (đã cào từ slider): {cat_url}")
                    continue

                msg = f"📂 [{i + 1}/{total_cats}] Đang xử lý: {cat_url}"
                print(msg)
                if progress_callback: progress_callback(msg)

                try:
                    driver.get(cat_url)
                    time.sleep(3)

                    page_count = 1

                    while True:
                        # Chờ và scroll (Chống sót)
                        try:
                            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, item_selector)))
                        except:
                            break

                        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                        time.sleep(2)

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

                        if current_links_count == 0 and page_count > 1:
                            break

                            # Chuyển trang (Archive)
                        try:
                            next_btn = driver.find_element(By.XPATH, NEXT_BTN_XPATH_ARCHIVE)
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
        # ... (Giữ nguyên hàm parse_detail) ...
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


# --- CLASS 5: Slabstone (Xử lý AJAX Pagination & Đa Tab chi tiết) ---
class SlabstoneScraper(BaseScraper):

    def get_links(self, url, item_selector, link_selector=None, progress_callback=None):
        driver = None
        product_links = set()

        # Selector nút Next
        NEXT_BTN_SELECTOR = "a.tv-page.next"

        try:
            if progress_callback: progress_callback(f"🚀 Đang khởi động trình duyệt...")
            driver = self._setup_driver()

            if progress_callback: progress_callback(f"🔗 Đang truy cập: {url}")
            driver.get(url)
            time.sleep(3)

            page_count = 1

            while True:
                soup = BeautifulSoup(driver.page_source, 'html.parser')
                items = soup.select(item_selector)

                current_page_links = []
                for item in items:
                    tag = item.select_one(link_selector) if link_selector else item.select_one('a')
                    href = tag.get('href') if tag else None
                    if href:
                        if not href.startswith('http'): href = "https://slabstone.vn" + href
                        if href not in product_links:
                            product_links.add(href)
                            current_page_links.append(href)

                msg = f"📄 Trang {page_count}: Tìm thấy {len(current_page_links)} sản phẩm mới. (Tổng: {len(product_links)})"
                print(msg)
                if progress_callback: progress_callback(msg)

                if len(current_page_links) == 0 and page_count > 1:
                    print("🛑 Không có sản phẩm mới -> Đã đến trang cuối.")
                    break

                try:
                    next_btn = driver.find_element(By.CSS_SELECTOR, NEXT_BTN_SELECTOR)
                    if not next_btn.is_displayed():
                        print("🚫 Nút Next bị ẩn -> Hết trang.")
                        break

                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", next_btn)
                    time.sleep(1)
                    driver.execute_script("arguments[0].click();", next_btn)

                    print(f"⏳ Đang tải trang {page_count + 1}...")
                    time.sleep(3)  # Chờ AJAX load
                    page_count += 1
                except Exception:
                    print(f"🛑 Không tìm thấy nút Next (Hoặc đã hết trang).")
                    break

        except Exception as e:
            if progress_callback: progress_callback(f"❌ Lỗi Selenium: {e}")
            print(f"Error: {e}")
        finally:
            if driver: driver.quit()

        return list(product_links)

    # --- HÀM PHỤ ĐỂ LẤY THÔNG SỐ TỪ 1 PANEL ---
    def _parse_specs_from_panel(self, container):
        specs = {}
        # Tìm các dòng thông số trong class .tv-info-grid .item
        items = container.select('.item')
        for item in items:
            lbl = item.select_one('label')
            val_p = item.select_one('p')
            val_img = item.select_one('.item-img img')  # Trường hợp Công nghệ xương là ảnh

            if lbl:
                key = lbl.text.strip().replace(':', '')
                val = "N/A"
                if val_p:
                    val = val_p.text.strip()
                elif val_img:
                    # Nếu giá trị là ảnh (ví dụ icon VeinTech), lấy link ảnh
                    val = val_img.get('src')

                if key and val:
                    specs[key] = val
        return specs

    def parse_detail(self, soup, url):
        try:
            # 1. Tên chung sản phẩm
            name_tag = soup.select_one('h1.elementor-heading-title')
            product_name = name_tag.text.strip() if name_tag else "N/A"

            # 2. Mô tả chung
            desc_tag = soup.select_one('.elementor-widget-theme-post-content')
            description = desc_tag.text.strip() if desc_tag else ""

            # 3. Ảnh (Lấy từ Slider, lọc trùng)
            images = []
            img_tags = soup.select('.swiper-slide:not(.swiper-slide-duplicate) img')
            for img in img_tags:
                src = img.get('src')
                if src: images.append(src)
            images = list(set(images))

            # 4. XỬ LÝ ĐA BIẾN THỂ (TABs) [QUAN TRỌNG]
            variants = []

            # Tìm danh sách các Tab (Mã sản phẩm: SP82H127, SM82H127...)
            tab_navs = soup.select('.tv-tab-nav li')

            if tab_navs:
                # Nếu có nhiều Tab
                for li in tab_navs:
                    variant_code = li.text.strip()  # Lấy tên mã (VD: SP82H127)
                    panel_id = li.get('data-tab')  # Lấy ID của panel chứa dữ liệu (VD: tv-tab-0)

                    # Tìm panel tương ứng trong HTML
                    panel = soup.select_one(f'#{panel_id}')
                    if panel:
                        # Gọi hàm phụ để lấy thông số kỹ thuật của panel này
                        specs = self._parse_specs_from_panel(panel)

                        # Thêm vào danh sách biến thể
                        variants.append({
                            "Mã": variant_code,
                            **specs  # Gộp các thông số (Kích thước, Độ dày...)
                        })
            else:
                # Trường hợp không có Tab (chỉ có 1 loại duy nhất)
                # Thử tìm bảng thông số trực tiếp
                panel = soup.select_one('.tv-info-grid')
                if panel:
                    specs = self._parse_specs_from_panel(panel)
                    variants.append({
                        "Mã": "Tiêu chuẩn",
                        **specs
                    })

            # 5. Trả về dữ liệu
            return {
                'URL': url,
                'Tên Sản Phẩm': product_name,
                'Mô tả': description,
                'Ảnh Đại Diện': images[0] if images else "N/A",
                'Danh Sách Ảnh': images,
                'Chi Tiết Các Mã': variants  # Trả về danh sách các biến thể
            }
        except Exception as e:
            print(f"Lỗi parse Slabstone: {e}")
            return None


# --- CLASS 6: Amy.vn (Full: Quét Menu + Cuộn trang + Parse chi tiết chuẩn) ---
class AmyScraper(BaseScraper):

    def get_links(self, url, item_selector, link_selector=None, progress_callback=None):
        driver = None
        product_links = set()

        try:
            if progress_callback: progress_callback(f"🚀 Đang khởi động trình duyệt...")
            driver = self._setup_driver()
            # Amy.vn load animation khá lâu, chờ tối đa 20s
            wait = WebDriverWait(driver, 20)

            # --- GIAI ĐOẠN 1: TỰ ĐỘNG LẤY LINK DANH MỤC TỪ MENU ---
            target_categories = []

            # Kiểm tra nếu là trang chủ
            is_homepage = "amy.vn" in url and len(url.split('/')) < 4

            if is_homepage:
                if progress_callback: progress_callback(f"⏳ Đang truy cập trang chủ và chờ Menu...")
                driver.get(url)

                try:
                    # Chờ menu xuất hiện
                    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, ".sub-menu-drop")))

                    soup = BeautifulSoup(driver.page_source, 'html.parser')
                    # Lấy tất cả link trong menu con
                    menu_items = soup.select('.sub-menu-drop .item-menu-second a')

                    for item in menu_items:
                        href = item.get('href')
                        name = item.text.strip()
                        if href:
                            if not href.startswith('http'): href = "https://amy.vn" + href
                            target_categories.append(href)
                            print(f"   -> Tìm thấy danh mục: {name}")

                except Exception as e:
                    print(f"⚠️ Không lấy được menu (Lỗi: {e}). Sẽ thử cào URL hiện tại.")
                    target_categories.append(url)
            else:
                target_categories.append(url)

            target_categories = list(set(target_categories))
            if progress_callback: progress_callback(
                f"✅ Đã tìm thấy {len(target_categories)} danh mục. Bắt đầu quét sản phẩm.")

            # --- GIAI ĐOẠN 2: DUYỆT TỪNG DANH MỤC & CUỘN VÔ TẬN ---
            total_cats = len(target_categories)
            for i, cat_url in enumerate(target_categories):
                msg = f"📂 [{i + 1}/{total_cats}] Đang xử lý: {cat_url}"
                print(msg)
                if progress_callback: progress_callback(msg)

                try:
                    driver.get(cat_url)
                    time.sleep(5)  # Chờ load trang danh mục

                    # Logic cuộn trang (Infinite Scroll)
                    last_height = driver.execute_script("return document.body.scrollHeight")
                    scroll_retries = 0

                    while True:
                        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                        time.sleep(3)  # Chờ sản phẩm mới load lên

                        new_height = driver.execute_script("return document.body.scrollHeight")
                        if new_height == last_height:
                            scroll_retries += 1
                            if scroll_retries >= 2: break  # Hết trang
                        else:
                            scroll_retries = 0
                            last_height = new_height

                        # (Tùy chọn) In ra số lượng tạm thời
                        # items_now = len(driver.find_elements(By.CSS_SELECTOR, item_selector))
                        # print(f"   ...Đã load {items_now} sản phẩm")

                    # Sau khi cuộn xong, parse HTML 1 lần để lấy link
                    soup_cat = BeautifulSoup(driver.page_source, 'html.parser')
                    items = soup_cat.select(item_selector)

                    count_new = 0
                    for item in items:
                        # Link nằm trong thẻ a có class .link-load hoặc .more-details
                        tag = item.select_one(link_selector) if link_selector else item.select_one('a')
                        href = tag.get('href') if tag else None

                        if href:
                            if not href.startswith('http'): href = "https://amy.vn" + href
                            if href not in product_links:
                                product_links.add(href)
                                count_new += 1

                    print(f"   -> Lấy được {count_new} sản phẩm mới.")

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
        try:
            # 1. Tên sản phẩm (Thẻ h1)
            name_tag = soup.select_one('h1')
            product_name = name_tag.text.strip() if name_tag else "N/A"

            # 2. Hình ảnh
            # Ảnh nằm trong .details-pics -> .slidebox-item -> img
            images = []
            img_tags = soup.select('.details-pics .slidebox-item img')
            for img in img_tags:
                src = img.get('src') or img.get('data-src')
                if src:
                    if not src.startswith('http'): src = "https://amy.vn" + src
                    images.append(src)
            images = list(set(images))  # Lọc trùng

            # 3. Thông số kỹ thuật (Dựa trên HTML bạn gửi)
            specs = {}

            # Tìm div chứa thông tin
            info_container = soup.select_one('.product-info.data-index')

            if info_container:
                # Tìm các thẻ h3 class="des-item"
                items = info_container.select('.des-item')
                for item in items:
                    # Key nằm trong span, Value nằm trong strong
                    key_tag = item.select_one('span')
                    val_tag = item.select_one('strong')

                    if key_tag and val_tag:
                        # Xóa dấu : ở key (VD: "Mã:" -> "Mã")
                        key = key_tag.text.replace(':', '').strip()
                        value = val_tag.text.strip()
                        specs[key] = value

            return {
                'URL': url,
                'Tên Sản Phẩm': product_name,
                'Ảnh Đại Diện': images[0] if images else "N/A",
                'Danh Sách Ảnh': images,
                **specs  # Gộp Mã, Giá, Thương hiệu, Kích thước, Bề mặt, Xương...
            }
        except Exception as e:
            print(f"Lỗi parse Amy: {e}")
            return None