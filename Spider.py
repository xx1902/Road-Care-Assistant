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

high_res_urls = []

# 处理每张缩略图
for index, thumbnail in enumerate(thumbnails, 1):
    print(f"正在处理第 {index}/{len(thumbnails)} 张图片")

    try:
        # 过滤小尺寸图片
        width = thumbnail.get_attribute("width")
        height = thumbnail.get_attribute("height")
        if not width or not height or int(width) <= 50 or int(height) <= 50:
            continue

        retries = 3
        while retries > 0:
            try:
                # 点击缩略图
                ActionChains(browser).move_to_element(thumbnail).click().perform()
                time.sleep(1)

                # 获取高清图
                try:
                    high_res_img = WebDriverWait(browser, 5).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "img[jsname='kn3ccd']")))
                    img_url = high_res_img.get_attribute("src")
                    if img_url:
                        high_res_urls.append(img_url)
                        break
                except TimeoutException:
                    break

            except StaleElementReferenceException:
                retries -= 1
                if retries == 0:
                    print("达到最大重试次数")
                time.sleep(1)

    except Exception as e:
        print(f"图片处理出错: {e}")

# 下载图片
if not os.path.exists("高清图片"):
    os.makedirs("高清图片")

for i, url in enumerate(high_res_urls):
    try:
        if url.startswith("data:image"):
            # 处理base64编码图片
            header, data = url.split(",", 1)
            with open(f"高清图片/{i}.jpg", "wb") as f:
                f.write(base64.b64decode(data))
        else:
            # 下载普通URL图片
            response = requests.get(url, timeout=10)
            with open(f"高清图片/{i}.jpg", "wb") as f:
                f.write(response.content)
        print(f"成功下载第 {i} 张图片")
    except Exception as e:
        print(f"图片下载失败: {e}")

browser.quit()

