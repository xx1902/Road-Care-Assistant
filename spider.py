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
import threading
from concurrent.futures import ThreadPoolExecutor
import imagehash
import json

CHECKPOINT_FILE = "./temp/crawl_checkpoint.json"
processed_hashes = None
image_lock = threading.Lock()
checkpoint = None
hash_lock = threading.Lock()
phash_set = set()

def load_checkpoint():
    """加载上次的爬取进度"""
    if os.path.exists(CHECKPOINT_FILE):
        with open(CHECKPOINT_FILE, 'r') as f:
            data = json.load(f)
            return {
                "processed_hashes": set(data["processed_hashes"]),
                "last_index": data["last_index"]
            }
    return {
        "processed_hashes": set(),
        "last_index": 0
    }

def save_checkpoint(checkpoint):
    """保存当前进度"""
    with open(CHECKPOINT_FILE, 'w') as f:
        json.dump({
            "processed_hashes": list(checkpoint["processed_hashes"]),
            "last_index": checkpoint["last_index"]
        }, f)


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


def download_image(savepath, img_url):
    # 下载图片数据
    try:
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
            if current_hash in processed_hashes:
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
        filename = f"{savepath}/{current_hash}.jpg"
        with open(filename, "wb") as f:
            f.write(img_data)

        with hash_lock:
            processed_hashes.add(current_hash)
            checkpoint["processed_hashes"].add(current_hash)
            save_checkpoint(checkpoint)
        with image_lock:
            phash_set.add(calculate_phash(img_pil))

        print(f"成功保存: {filename}")
    except Exception as e:
        print(f"下载失败: {str(e)}")


def spider(savepath, search_word):

    global processed_hashes, checkpoint

    options = webdriver.ChromeOptions()
    options.add_argument("--disable-infobars")
    options.add_argument("--disable-dev-shm-usage")
    browser = webdriver.Chrome(options=options)
    browser.set_window_size(1500, 1000)
    browser.get("https://www.google.com/imghp")

    search_box = browser.find_element(By.NAME, "q")
    search_box.send_keys(search_word) 
    search_box.submit()
    time.sleep(2)

    checkpoint = load_checkpoint()

    print(1)
    print(checkpoint)

    processed_hashes = set(checkpoint["processed_hashes"])
    last_index = checkpoint["last_index"]

    print(last_index)

    max_scroll_attempts = 20
    scroll_attempt = 0
    while True:
        WebDriverWait(browser, 10).until(
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, "img.YQ4gaf"))
        )
        thumbnails = browser.find_elements(By.CSS_SELECTOR, "img.YQ4gaf")

        if len(thumbnails) > last_index or scroll_attempt >= max_scroll_attempts:
            break

        browser.execute_script("window.scrollBy(0, 2000)")
        time.sleep(1.5)
        scroll_attempt += 1

    print(f"找到 {len(thumbnails)} 张缩略图，从索引 {last_index} 开始处理")

    if not os.path.exists(savepath):
        os.makedirs(savepath)


    with ThreadPoolExecutor(max_workers=4) as executor:
        for offset, thumbnail in enumerate(thumbnails[last_index:]):
            current_index = last_index + offset
            print(f"正在处理第 {current_index + 1}/{len(thumbnails)} 张缩略图")

            try:
                width = thumbnail.get_attribute("width")
                height = thumbnail.get_attribute("height")
                if not width or not height or int(width) <= 50 or int(height) <= 50:
                    continue

                retries = 3
                while retries > 0:
                    try:
                        ActionChains(browser).move_to_element(thumbnail).click().perform()
                        time.sleep(1)

                        high_res_img = WebDriverWait(browser, 3).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, "img[jsname='kn3ccd']"))
                        )
                        img_url = high_res_img.get_attribute("src")

                        if img_url:
                            executor.submit(download_image, savepath, img_url)
                            with hash_lock:
                                checkpoint["last_index"] = current_index
                                save_checkpoint(checkpoint)
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

    try:
        browser.quit()
    except:
        pass


if __name__ == "__main__":
    spider("./temp/images","car accident")