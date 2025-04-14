from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import StaleElementReferenceException, TimeoutException
import time
import requests
import os
import base64
import hashlib
from PIL import Image
import io
import numpy as np
from skimage.metrics import structural_similarity as ssim
import threading
from concurrent.futures import ThreadPoolExecutor
import imagehash

# 初始化浏览器
options = webdriver.ChromeOptions()
options.add_argument("--disable-infobars")
options.add_argument("--disable-dev-shm-usage")
browser = webdriver.Chrome(options=options)
browser.set_window_size(1500, 1000)
browser.get("https://www.google.com/imghp")

# 搜索图片
search_box = browser.find_element(By.NAME, "q")
search_box.send_keys("car accident")  # 改为中文关键词
search_box.submit()
time.sleep(2)

# 滚动加载更多图片
for _ in range(1):
    browser.execute_script("window.scrollBy(0, 1000)")
    time.sleep(1)

# 等待缩略图加载
WebDriverWait(browser, 5).until(
    EC.presence_of_all_elements_located((By.CSS_SELECTOR, "img.YQ4gaf"))
)

thumbnails = browser.find_elements(By.CSS_SELECTOR, "img.YQ4gaf")
print(f"找到 {len(thumbnails)} 张缩略图")

# 创建保存目录
if not os.path.exists("高清图片"):
    os.makedirs("高清图片")

# 线程安全数据结构
hash_lock = threading.Lock()
image_lock = threading.Lock()
saved_hashes = set()
phash_set = set()

# 初始化时加载已有哈希
for filename in os.listdir("高清图片"):
    if filename.endswith(('.jpg', '.jpeg', '.png')):
        try:
            with open(os.path.join("高清图片", filename), 'rb') as f:
                file_hash = hashlib.md5(f.read()).hexdigest()
                with hash_lock:
                    saved_hashes.add(file_hash)
        except:
            continue


def calculate_phash(image):
    """计算感知哈希"""
    try:
        return imagehash.phash(image.convert('L').resize((64, 64)))
    except:
        return None


def is_duplicate(img_pil):
    """检查相似图片"""
    current_phash = calculate_phash(img_pil)
    if current_phash is None:
        return False

    with image_lock:
        for phash in phash_set:
            if current_phash - phash < 5:  # 相似度阈值
                return True
        return False


def download_image(img_url):
    """下载并保存单张图片"""
    try:
        # 下载图片数据
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }

        if img_url.startswith("data:image"):
            try:
                header, data = img_url.split(",", 1)
                img_data = base64.b64decode(data)
            except (ValueError, binascii.Error) as e:
                print(f"Base64解码失败: {e}")
                return
        else:
            try:
                response = requests.get(img_url, headers=headers, timeout=15)
                response.raise_for_status()
                img_data = response.content
            except Exception as e:
                print(f"下载失败: {str(e)}")
                return

        # 验证数据有效性
        if len(img_data) < 1024:
            print(f"图片数据过小({len(img_data)} bytes)")
            return

        # 计算哈希值
        current_hash = hashlib.md5(img_data).hexdigest()
        with hash_lock:
            if current_hash in saved_hashes:
                print(f"重复哈希: {current_hash[:8]}...")
                return

        # 验证图片完整性
        try:
            img_pil = Image.open(io.BytesIO(img_data))
            img_pil.verify()
            img_pil = Image.open(io.BytesIO(img_data))  # 重新打开
        except Exception as e:
            print(f"图片验证失败: {str(e)}")
            return

        # 相似性检查
        if is_duplicate(img_pil):
            print(f"发现相似图片")
            return

        # 保存图片
        filename = f"高清图片/{current_hash}.jpg"
        with open(filename, "wb") as f:
            f.write(img_data)

        # 更新全局状态
        with hash_lock:
            saved_hashes.add(current_hash)
        with image_lock:
            phash_set.add(calculate_phash(img_pil))

        print(f"成功保存: {filename}")

    except Exception as e:
        print(f"处理异常: {str(e)}")


# 使用线程池管理并发
with ThreadPoolExecutor(max_workers=4) as executor:
    for index, thumbnail in enumerate(thumbnails, 1):
        print(f"正在处理第 {index}/{len(thumbnails)} 张缩略图")

        try:
            # 过滤小尺寸图片
            width = thumbnail.get_attribute("width")
            height = thumbnail.get_attribute("height")
            if not width or not height or int(width) <= 50 or int(height) <= 50:
                continue

            retries = 3
            while retries > 0:
                try:
                    ActionChains(browser).move_to_element(thumbnail).click().perform()
                    time.sleep(0.5)

                    high_res_img = WebDriverWait(browser, 3).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "img[jsname='kn3ccd']"))
                    )
                    img_url = high_res_img.get_attribute("src")

                    if img_url:
                        executor.submit(download_image, img_url)
                    break

                except StaleElementReferenceException:
                    retries -= 1
                    if retries == 0:
                        print("达到最大重试次数")
                    time.sleep(1)
                except TimeoutException:
                    break

        except Exception as e:
            print(f"缩略图处理异常: {str(e)}")

# 确保浏览器关闭
try:
    browser.quit()
except:
    pass