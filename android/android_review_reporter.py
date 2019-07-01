# global
import argparse
import csv
import os
import string
import subprocess
import sys
import json
import re
import datetime as dt

# dependencies
import requests
from bs4 import BeautifulSoup
from google.cloud import translate

# custom
cur_dir = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, f'{cur_dir}/..')
from log import Log


today = dt.datetime.today().strftime('%Y%m%d')


def read_json(jpath):
    with open(jpath, 'r') as f:
        json_data = json.load(f)
    return json_data


def load_recorded_review_date(rpath):
    if os.path.isfile(rpath):
        recorded_recent_review = read_json(rpath)
    else:
        logh.write_info(
            f'Not found recent_review_file, it will be made in {rpath}')
        recorded_recent_review = {}
    return recorded_recent_review


def jsonify_data(data):
    json_data = json.loads(data)
    return json_data


def get_reviews_part(str_data):
    soup = BeautifulSoup(str_data)
    reviews = soup.find_all('div', class_='single-review')
    return reviews


def extract_required_field_review(data, lcode, lang):
    review_date = _get_review_date(data)
    translated_review_date = _translate_text(review_date)
    review_date_int = _reform_to_date(translated_review_date)
    author_name = _get_author_name(data)
    review_rate = _get_review_rating(data)
    review_title = _get_review_title(data)
    tranaslated_title = _translate_text(text=review_title)
    refined = [
        review_date_int,
        today,
        lcode,
        lang,
        author_name,
        review_rate,
        review_title,
        tranaslated_title
    ]
    return refined


def _get_review_date(data):
    review_date = data.find('span', class_='review-date').text.strip()
    return review_date


def _get_author_name(data):
    author_name = data.find('span', class_='author-name').text.strip()
    return author_name


def _get_review_rating(data):
    rating_part = data.find('div', class_='review-info-star-rating')
    rating_word = rating_part.div['aria-label']
    nums = re.findall(r'[0-9]', rating_word)
    if nums and len(nums) == 2:
        five_idx = nums.index('5')
        nums.pop(five_idx)
        rating = nums[0]
    else:
        rating = rating_word
    return rating


def _get_review_title(data):
    review_body = data.find('div', class_='review-body').text
    review_title = review_body.replace('전체 리뷰', '').strip()
    return review_title


def _translate_text(text, country_code=None):
    translate_client = translate.Client()
    if country_code in ['kr', 'us']:
        translated_text = text
    else:
        lang = translate_client.detect_language(text)
        if lang in ['ko', 'en']:
            translated_text = text
        else:
            translation = translate_client.translate(
                text, target_language='en')
            translated_text = translation['translatedText']
    return translated_text


def _reform_to_date(origin):
    refined = origin.replace(',', '')
    if refined[0].isdigit():
        reform_pattern = '%d %B %Y'
    else:
        reform_pattern = '%B %d %Y'
    reform = dt.datetime.strptime(refined, reform_pattern).strftime('%Y%m%d')
    return int(reform)


def get_data_from_url(url, params, header):
    res = requests.post(url, data=params, headers=header)
    return res.status_code, res.text


def get_new_reviews_in_page(page_data, recent, lcode, lang, recorded_recent_date):
    new_reviews = list()
    # because of )]}'\n\n, start from 6
    review_soup_list = get_reviews_part(page_data)
    for review_soup in review_soup_list:
        refined_review = extract_required_field_review(
            review_soup, lcode, lang)
        review_date = refined_review[0]
        if review_date <= recorded_recent_date:
            recent = False
            logh.write_info(
                f'lang: {lcode}, review date: {review_date}, recorded: {recorded_recent_date}')
            break
        new_reviews.append(refined_review)
    return new_reviews, recent


def get_all_new_reviews_in_lcode(appid, lcode, lang, lcode_recent_date, url, url_header, params):
    all_new_reviews = list()
    pagenum = 0
    recent = True
    while recent:
        params['pageNum'] = str(pagenum)
        params['hl'] = lcode
        res_code, res_text = get_data_from_url(url, params, url_header)
        if res_code != 200:
            logh.write_warn(f'{lcode} fail to connect, code: {res_code}')
            break
        else:
            json_data = jsonify_data(res_text[6:])
            review_part = json_data[0][2]

            if review_part:
                new_reviews, recent = get_new_reviews_in_page(
                    review_part, recent, lcode, lang, lcode_recent_date)
                all_new_reviews.extend(new_reviews)
            else:
                logh.write_warn(f'No reviews in page {pagenum} of {lcode}')
                break
    return all_new_reviews


def update_recorded_date(new_reviews, recorded_review_date_book, lcode):
    if new_reviews:
        recent_date = new_reviews[0][0]
        recorded_review_date_book[lcode] = recent_date
    return recorded_review_date_book


def save_json_data(rpath, data):
    with open(rpath, 'w+') as f:
        json.dump(data, f, indent=4)
    return True


def save_csv(outpath, data, header):
    if data:
        with open(outpath, 'w+', encoding='utf-8-sig') as f:
            cw = csv.writer(f)
            cw.writerow(header)
            for line in data:
                cw.writerow(line)
        result = True
    else:
        result = False
    return result


def get_arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--app_id',
        type=str,
        required=True,
        help='android appid of which want to scrape review'
    )
    parser.add_argument(
        '--lang_code_path',
        type=str,
        default=f'{cur_dir}/google_language_codes.json'
    )
    parser.add_argument(
        '--recent_review_path',
        type=str,
        default=f'{cur_dir}/recent_review_android.json'
    )
    parser.add_argument(
        '--log_path',
        type=str,
        default=f'{cur_dir}/android_review_reporter.log'
    )
    parser.add_argument(
        '--outdir',
        type=str,
        default=cur_dir
    )
    args = parser.parse_args()
    return args


def main():
    args = get_arguments()
    appid = args.app_id
    outdir = args.outdir
    lang_code_path = args.lang_code_path
    recorded_date_path = args.recent_review_path
    global logh
    logh = Log(args.log_path)

    logh.write_info(f'app id: {appid}')

    # default setting
    logh.write_info(f'check date: {today}')

    save_path = f'{outdir}/reviews_android_{today}.csv'
    csv_header = [
        'reviewDate', 'updateDate', 'langCode', 'language',
        'authorName', 'rating', 'reviewTitle', 'translatedTitle'
    ]
    url = 'https://play.google.com/store/getreviews'
    url_headers = {
        'Content-Type': 'application/x-www-form-urlencoded;charset=utf-8'}
    # reviewSortOrder 0: 최신 1: 높은 평점 2: 유용
    params = {
        'reviewType': '0',
        'pageNum': '',
        'id': appid,
        'reviewSortOrder': '0',
        'hl': '',
        'xhr': '1'
    }

    lang_dict = read_json(lang_code_path)
    recorded_review_date_book = load_recorded_review_date(recorded_date_path)
    world_new_reviews = list()
    for lcode in lang_dict:
        lang = lang_dict.get(lcode)
        recorded_date = recorded_review_date_book.get(lcode, 0)
        logh.write_info(
            f'langcode: {lcode}, recorded_recent_date: {recorded_date}'
        )
        new_reviews_of_country = get_all_new_reviews_in_lcode(
            appid, lcode, lang, recorded_date, url, url_headers, params
        )
        logh.write_info(f'new_data: {len(new_reviews_of_country)}')
        world_new_reviews.extend(new_reviews_of_country)
        recorded_review_date_book = update_recorded_date(
            new_reviews_of_country, recorded_review_date_book, lcode
        )

    recorded_recent_update = save_json_data(
        recorded_date_path, recorded_review_date_book
    )
    logh.write_info(f'review updated: {recorded_recent_update}')
    is_updated = save_csv(save_path, world_new_reviews, csv_header)
    logh.write_info(f'save as csv file: {is_updated}')


if __name__ == '__main__':
    main()
