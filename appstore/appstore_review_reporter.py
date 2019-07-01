# global
import argparse
import csv
import datetime as dt
import urllib.request
import string
import subprocess
import sys
import os
import json
import re

# dependencies
from google.cloud import translate

# custom
cur_dir = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, f'{cur_dir}/..')
from log import Log


def load_recorded_recent_review(rpath):
    if os.path.isfile(rpath):
        recorded_recent_review = _read_json(rpath)
    else:
        recorded_recent_review = {}
    return recorded_recent_review


def _read_json(jpath):
    with open(jpath, 'r') as f:
        data = json.load(f)
    return data


def get_json_data_from_url(url):
    with urllib.request.urlopen(url) as f:
        data = json.loads(f.read())
    return data


def refine_only_text(raw_data):
    raw_data = raw_data.replace('\n', ' ')
    pre_data = re.sub(r'[' + string.punctuation + ']', '', raw_data)
    only_text = re.sub(r' +', ' ', pre_data)
    return only_text


def translate_text(text, country_code):
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


def save_csv(outpath, data, header):
    with open(outpath, 'w+', encoding='utf-8-sig') as f:
        cw = csv.writer(f)
        cw.writerow(header)
        for line in data:
            cw.writerow(line)
    return True


def update_recent_reviews(appid, country_code_book, recorded_recent_review):
    is_updated = False
    world_recent_review_data = list()
    for country_code in country_code_book:
        translated_tit = ''
        translated_cont = ''
        country = country_code_book[country_code]
        review_parts = _extract_app_review_parts(appid, country_code)

        if review_parts:
            country_recorded_recent_review_id = recorded_recent_review.get(
                country_code, 0)
            country_reviews, is_updated = _get_country_reviews(
                review_parts,
                country_recorded_recent_review_id,
                country_code,
                country
            )

        if is_updated:
            recorded_recent_review[country_code] = is_updated
            world_recent_review_data.extend(country_reviews)
        else:
            continue
    return world_recent_review_data, recorded_recent_review


def _extract_app_review_parts(app_id, country_code):
    url = f'https://itunes.apple.com/{country_code}/rss/customerreviews/id={app_id}/sortBy=mostRecent/json'
    raw_data = get_json_data_from_url(url)
    reviews = raw_data['feed'].get('entry')
    reviews = [reviews] if type(reviews) is dict else reviews
    return reviews


def _get_country_reviews(review_cards, recent_review_id, country_code, country):
    review_data = list()
    updated = False
    for card in review_cards:
        review_id = int(card['id']['label'])
        if review_id > recent_review_id and updated is False:
            updated = review_id
        elif review_id <= recent_review_id:
            continue
        members = _extract_required_content(card, country_code, country)
        review_data.append(members)
    return review_data, updated


def _extract_required_content(raw_review_data, country_code, country):
    app_version = raw_review_data['im:version'].get('label')
    review_id = int(raw_review_data['id']['label'])
    rating = raw_review_data['im:rating']['label']
    title = refine_only_text(raw_review_data['title']['label'])
    translated_tit = translate_text(title, country_code)
    content = refine_only_text(raw_review_data['content']['label'])
    translated_cont = translate_text(content, country_code)
    required_content = [
        review_id,
        app_version,
        country_code,
        country,
        rating,
        title,
        content,
        translated_tit,
        translated_cont
    ]
    return required_content


def update_recorded_recent_review(rpath, data):
    with open(rpath, 'w+') as f:
        json.dump(data, f, indent=4)
    return True


def get_arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--app_id',
        type=int,
        required=True,
        help='appstore appid of which want to scrape review'
    )
    parser.add_argument(
        '--country_code_path',
        type=str,
        default=f'{cur_dir}/itunes_country_codes.json'
    )
    parser.add_argument(
        '--recent_review_path',
        type=str,
        default=f'{cur_dir}/recent_review_appstore.json'
    )
    parser.add_argument(
        '--log_path',
        type=str,
        default=f'{cur_dir}/appstore_review_reporter.log'
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
    log_path = args.log_path
    outdir = args.outdir
    app_id = args.app_id
    country_code_file_path = args.country_code_path
    # recent review => country_code: id
    recent_review_file_path = args.recent_review_path

    logh = Log(log_path)
    logh.write_info(f'app_id: {app_id}')

    # default settings
    header = ['id', 'appVersion', 'code', 'country', 'rating',
              'title', 'content', 'translated_tit', 'translated_cont']
    today = dt.datetime.today().strftime('%Y%m%d')
    save_path = f'{outdir}/reviews_appstore_{today}.csv'

    logh.write_info(f'check date: {today}')

    country_code_book = _read_json(country_code_file_path)
    recorded_recent_review = load_recorded_recent_review(
        recent_review_file_path
    )

    recent_reviews, recorded_recent = update_recent_reviews(
        app_id, country_code_book,
        recorded_recent_review
    )

    logh.write_info(f'recent reviews: {len(recent_reviews)}')

    update_recorded = update_recorded_recent_review(
        recent_review_file_path,
        recorded_recent
    )

    if recent_reviews:
        csv_data = save_csv(save_path, recent_reviews, header)
        logh.write_info(f'save review data as csv file: {csv_data}')
    else:
        logh.write_info(f'There is nothing to be updated in {today}')


if __name__ == '__main__':
    main()
