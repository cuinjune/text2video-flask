import sys
import os
import json
from collections import Counter
import spacy
from flask import Flask, request
from gevent.pywsgi import WSGIServer
from decouple import config
from pixabay import Image, Video

nlp = spacy.load("en_core_web_md")

def get_keywords(text):
    doc = nlp(text)
    entities = [e.text for e in list(doc.ents) if e.label_ in ["PERSON", "NORP", "FAC", "ORG", "GPE", "LOC", "PRODUCT", "EVENT"]]
    words = [w.text for w in list(doc) if w.is_alpha and not w.is_stop and not w.is_punct and w.tag_ in ["NN", "NNS", "NNP", "NNPS", "VB", "VBD", "VBG", "VBP", "VBZ", "AFX", "JJ"]]
    return  words + entities

# keywords test mode (by passing a sentence as arguments)
if len(sys.argv) > 1:
    # get text from system arguments
    sentence = " ".join(sys.argv[1:])
    keywords = get_keywords(sentence)
    keywords = [k[0] for k in Counter(keywords).most_common(5)] # keywords to search in order
    print("keywords", keywords)
    exit()
    
app = Flask(__name__)
PORT = int(os.environ.get("PORT", 3000))
PIXABAY_API_AUTH_KEY = os.environ.get(
    "PIXABAY_API_AUTH_KEY", config("PIXABAY_API_AUTH_KEY") or "Your API key from https://pixabay.com/api/docs/")

video = Video(PIXABAY_API_AUTH_KEY)
image = Image(PIXABAY_API_AUTH_KEY)

def get_updated_data(data):
    # avoid using repeated or cors blocked contents
    video_ids = set([15333])
    image_ids = set()
    for sentence in data["sentences"]:
        # per sentence
        min_duration = sentence["time"] / 1000
        max_duration = 60
        keywords = get_keywords(sentence["value"]) or [sentence["value"]]
        doc_keywords = nlp(" ".join(keywords)) # used for similarity
        keywords = [k[0] for k in Counter(keywords).most_common(5)] # keywords to search in order
        print("sentence:", sentence["value"], "\nkeywords", keywords)
        id_ = 0
        url = ""
        for keyword in keywords:
            # per keyword
            max_similarity = 0
            max_hit = dict()
            for hit in video.search(q=keyword, per_page=200)["hits"]:
                if  min_duration <= hit["duration"] <= max_duration and hit["id"] not in video_ids:
                    similarity = doc_keywords.similarity(nlp(hit["tags"].replace(",", "")))
                    if similarity > max_similarity:
                        max_similarity = similarity
                        max_hit = hit
            if max_similarity > 0.5 and max_hit:
                id_ = max_hit["id"]
                video_ids.add(id_);
                url = max_hit["videos"]["medium"]["url"]
                break
        if not url:
            for keyword in keywords:
                # per keyword
                max_similarity = 0
                max_hit = dict()
                for hit in image.search(q=keyword, per_page=200)["hits"]:
                    if hit["id"] not in image_ids:
                        similarity = doc_keywords.similarity(nlp(hit["tags"].replace(",", "")))
                        if similarity > max_similarity:
                            max_similarity = similarity
                            max_hit = hit
                if max_similarity > 0.5 and max_hit:
                    id_ = max_hit["id"]
                    image_ids.add(id_);
                    url = max_hit["webformatURL"]
                    break
            if not url and len(keywords):
                url = keywords[0].replace(",", "").capitalize()
        sentence["id"] = id_
        sentence["url"] = url
    return data

@app.route("/api/v1/flask/data", methods=["POST"])
def postdata():
    data = request.get_json()
    data = get_updated_data(data)
    return json.dumps(data)

if __name__ == "__main__":
    print("Listening on port:", PORT)
    http_server = WSGIServer(("", PORT), app)
    http_server.serve_forever()