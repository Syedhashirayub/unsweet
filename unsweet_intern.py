import os 
import requests
from bs4 import BeautifulSoup
import csv
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from selenium.common.exceptions import NoSuchElementException
import time
from urllib.parse import urlparse, parse_qs

# Set up Selenium to load dynamic content
chrome_options = Options()
chrome_options.add_argument("--headless")  # Run headless to avoid opening a browser window
driver = webdriver.Chrome(options=chrome_options)
wait = WebDriverWait(driver, 20)  # Setup wait for a maximum of 15 seconds

# A function to normalize Amazon product URLs based on their ASIN
def normalize_amazon_url(url):
    # Parse the URL
    parsed_url = urlparse(url)
    # Extract query parameters into a dictionary
    query_params = parse_qs(parsed_url.query)
    # Extract the ASIN (Amazon Standard Identification Number)
    asin = query_params.get('asin')
    if asin:
        # Reconstruct the URL with only the ASIN as a query parameter
        normalized_url = f"{parsed_url.scheme}://{parsed_url.netloc}{parsed_url.path}?asin={asin[0]}"
        return normalized_url
    return url  # Return the original URL if ASIN is not found


def get_all_reviews_for_tag(driver, tag_url):
    driver.get(tag_url)
    try:
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div[data-hook='review']")))
    except TimeoutException:
        # If no reviews are found, return an empty list or a custom message
        print(f"No reviews found for tag URL: {tag_url}")
        return []

    reviews = []

    while True:
        soup = BeautifulSoup(driver.page_source, "html.parser")
        review_divs = soup.find_all("div", {"data-hook": "review"})

        for review_div in review_divs:
            review_texts = []
            for element in review_div.find("span", {"data-hook": "review-body"}).descendants:
                if isinstance(element, str):
                    review_texts.append(element.strip())
                elif element.name == 'br':
                    review_texts.append('\n')

            review_text = ' '.join(filter(None, review_texts))
            reviews.append(review_text)

        next_button = soup.find("li", {"class": "a-last"})
        if next_button and next_button.find("a"):
            next_page_url = "https://www.amazon.in" + next_button.find("a")["href"]
            driver.get(next_page_url)
            try:
                wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div[data-hook='review']")))
            except TimeoutException:
                print("Reached the last page of reviews or no additional reviews found.")
                break
            time.sleep(2)
        else:
            break

    return reviews

def get_product_details(product_url):
    driver.get(product_url)
    # Wait for the page to load and the product title to be present
    WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.ID, "productTitle")))

    # Scroll to the "customerReviews" section where the tags are loaded
    customer_reviews_section = WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.ID, "customerReviews")))
    driver.execute_script("arguments[0].scrollIntoView(true);", customer_reviews_section)

    # Wait for a short while to allow any lazy-loaded elements to appear
    time.sleep(5)  # Adjust the sleep time as necessary

    soup = BeautifulSoup(driver.page_source, "html.parser")
    product_name = "Product name not found"
    product_title_div = soup.find("div", {"id": "title_feature_div"})
    if product_title_div:
        product_name_span = product_title_div.find("span", {"id": "productTitle"})
        if product_name_span:
            product_name = product_name_span.get_text(strip=True)

    product_tags = []
    product_tag_links = []

    # Instead of waiting for the tags to be present, we know they are inside a div with id 'cr-dp-lighthut'.
    # We'll directly check for this div and parse it.
    lighthut_div = soup.find("div", {"id": "cr-dp-lighthut"})
    if lighthut_div:
        tags = lighthut_div.find_all("span", {"class": "cr-lighthouse-term"})
        for tag in tags:
            tag_a = tag.find_parent('a')
            if tag_a and 'href' in tag_a.attrs:
                tag_url = "https://www.amazon.in" + tag_a['href']
                tag_text = tag.get_text(strip=True)
                if tag_text:  # Ensure there is text
                    product_tags.append(tag_text)
                    product_tag_links.append(tag_url)
    else:
        # If the tags div is not found, print a message and continue
        print("Product tags section not found, continuing with next product.")

    return {
        'product_name': product_name,
        'product_url': product_url,
        'product_tags': product_tags,
        'product_tag_links': product_tag_links
    }



# Open the CSV file for writing
csv_filename = "/Volumes/Hardisc/unsweet/amazon_product_data.csv"

with open(csv_filename, "w", newline="", encoding="utf-8") as csv_file:
    csv_writer = csv.writer(csv_file)
    csv_writer.writerow(["Product name", "Product URL", "Product Tag", "Review"])

    base_url = "https://www.amazon.in"
    list_url = f"{base_url}/s?i=beauty&rh=n%3A1374407031&fs=true&qid=16934"
    processed_products = set()

    while list_url:
        driver.get(list_url)
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "a.a-link-normal.s-underline-text.s-underline-link-text.s-link-style.a-text-normal")))
        
        list_soup = BeautifulSoup(driver.page_source, "html.parser")
        product_links = list_soup.select('a.a-link-normal.s-underline-text.s-underline-link-text.s-link-style.a-text-normal')
        
        for link in product_links:
            product_url = base_url + link['href']
            normalized_product_url = normalize_amazon_url(product_url)  # Normalize the URL
            if normalized_product_url in processed_products:
                print(f"Product URL {normalized_product_url} has already been processed.")
                continue

            print(f"Processing product URL: {normalized_product_url}")
            product_details = get_product_details(product_url)
            processed_products.add(normalized_product_url)  # Add the normalized URL to the set
            
            if product_details['product_tags']:
                for tag, tag_url in zip(product_details['product_tags'], product_details['product_tag_links']):
                    reviews = get_all_reviews_for_tag(driver, tag_url)
                    for review in reviews:
                        csv_writer.writerow([product_details['product_name'], product_details['product_url'], tag, review])
            else:
                print(f"No tags found for product: {product_details['product_name']}")

        # Update the list_url for the next page if the 'Next' button exists
        next_page_link = list_soup.select_one('a.s-pagination-next')
        list_url = base_url + next_page_link['href'] if next_page_link and 'href' in next_page_link.attrs else None

driver.quit()


    