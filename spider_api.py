from flask import Flask, request, jsonify
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
import threading
from concurrent.futures import ThreadPoolExecutor
import imagehash
import json

app = Flask(__name__)


# 全局状态管理
class CrawlerState:
    def __init__(self):
        self.save_dir = None
        self.browser = None
        self.checkpoint_path = None
        self.is_running = False
        self.lock = threading.Lock()


state = CrawlerState()


def init_browser():
    options = webdriver.ChromeOptions()
    options.add_argument("--disable-infobars")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--headless")  # 无头模式
    return webdriver.Chrome(options=options)


def load_checkpoint(save_dir):
    checkpoint_path = os.path.join(save_dir, "crawl_checkpoint.json")
    if os.path.exists(checkpoint_path):
        with open(checkpoint_path, 'r') as f:
            data = json.load(f)
            return {
                "processed_hashes": set(data["processed_hashes"]),
                "last_index": data["last_index"]
            }
    return {
        "processed_hashes": set(),
        "last_index": 0
    }


def save_checkpoint(save_dir, checkpoint):
    checkpoint_path = os.path.join(save_dir, "crawl_checkpoint.json")
    os.makedirs(save_dir, exist_ok=True)
    with open(checkpoint_path, 'w') as f:
        json.dump({
            "processed_hashes": list(checkpoint["processed_hashes"]),
            "last_index": checkpoint["last_index"]
        }, f)


def crawler_task(save_dir):
    with state.lock:
        try:
            state.browser = init_browser()
            state.browser.set_window_size(1500, 1000)
            state.browser.get("https://www.google.com/imghp")

            # 搜索流程
            search_box = WebDriverWait(state.browser, 15).until(
                EC.presence_of_element_located((By.NAME, "q"))
            )
            search_box.send_keys("car accident")
            search_box.submit()
            time.sleep(3)

            # 加载检查点
            checkpoint = load_checkpoint(save_dir)
            processed_hashes = checkpoint["processed_hashes"]
            last_index = checkpoint["last_index"]

            # 滚动加载
            max_scroll_attempts = 20
            scroll_attempt = 0
            while True:
                thumbnails = state.browser.find_elements(By.CSS_SELECTOR, "img[jsname='Q4LuWd']")
                if len(thumbnails) > last_index + 5 or scroll_attempt >= max_scroll_attempts:
                    break
                state.browser.execute_script("window.scrollBy(0, 2000)")
                time.sleep(2)
                scroll_attempt += 1

            print(f"找到 {len(thumbnails)} 张缩略图，从索引 {last_index} 开始处理")

            # 线程安全控制
            hash_lock = threading.Lock()
            image_lock = threading.Lock()
            phash_set = set()

            def download_image(img_url):
                try:
                    headers = {
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}

                    if img_url.startswith("data:image"):
                        header, data = img_url.split(",", 1)
                        img_data = base64.b64decode(data)
                    else:
                        response = requests.get(img_url, headers=headers, timeout=20)
                        response.raise_for_status()
                        img_data = response.content

                    if len(img_data) < 2048:
                        return

                    current_hash = hashlib.md5(img_data).hexdigest()
                    with hash_lock:
                        if current_hash in processed_hashes:
                            return

                    img_pil = Image.open(io.BytesIO(img_data))
                    img_pil.verify()
                    img_pil = Image.open(io.BytesIO(img_data))

                    # 保存文件
                    filename = os.path.join(save_dir, f"{current_hash}.jpg")
                    with open(filename, "wb") as f:
                        f.write(img_data)

                    # 更新检查点
                    with hash_lock:
                        processed_hashes.add(current_hash)
                        new_checkpoint = {
                            "processed_hashes": processed_hashes,
                            "last_index": checkpoint["last_index"]
                        }
                        save_checkpoint(save_dir, new_checkpoint)

                except Exception as e:
                    print(f"下载失败: {str(e)}")

            # 处理缩略图
            with ThreadPoolExecutor(max_workers=4) as executor:
                for offset, thumbnail in enumerate(thumbnails[last_index:]):
                    current_index = last_index + offset
                    try:
                        if int(thumbnail.get_attribute("naturalWidth")) < 100:
                            continue

                        retries = 3
                        while retries > 0:
                            try:
                                ActionChains(state.browser).move_to_element(thumbnail).click().perform()
                                time.sleep(1)

                                high_res_img = WebDriverWait(state.browser, 10).until(
                                    EC.presence_of_element_located((By.CSS_SELECTOR, "img[jsname='kn3ccd']"))
                                )
                                img_url = high_res_img.get_attribute("src")

                                if img_url:
                                    executor.submit(download_image, img_url)
                                    with hash_lock:
                                        new_checkpoint["last_index"] = current_index
                                        save_checkpoint(save_dir, new_checkpoint)
                                break
                            except StaleElementReferenceException:
                                retries -= 1
                                time.sleep(2)
                            except TimeoutException:
                                break

                    except Exception as e:
                        print(f"处理异常: {str(e)}")

        finally:
            if state.browser:
                state.browser.quit()
            state.is_running = False


@app.route('/start', methods=['POST'])
def start_crawl():
    if state.is_running:
        return jsonify({"status": "error", "message": "已有任务在运行"}), 400

    data = request.json
    save_dir = data.get('save_dir')

    if not save_dir:
        return jsonify({"status": "error", "message": "需要提供保存路径"}), 400

    state.save_dir = save_dir
    state.is_running = True
    threading.Thread(target=crawler_task, args=(save_dir,)).start()
    return jsonify({"status": "success", "message": "任务已启动"})


@app.route('/status', methods=['GET'])
def get_status():
    return jsonify({
        "is_running": state.is_running,
        "save_dir": state.save_dir
    })


if __name__ == '__main__':
    app.run(port=5000, threaded=True)