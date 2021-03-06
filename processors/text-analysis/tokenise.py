"""
Tokenize post bodies
"""
import datetime
import zipfile
import shutil
import pickle
import re

from csv import DictReader
from nltk.stem.snowball import SnowballStemmer
from nltk.stem import WordNetLemmatizer
from nltk.tokenize import word_tokenize, TweetTokenizer

from backend.lib.helpers import UserInput
from backend.abstract.processor import BasicProcessor

import config

__author__ = ["Stijn Peeters", "Sal Hagen"]
__credits__ = ["Stijn Peeters", "Sal Hagen"]
__maintainer__ = ["Stijn Peeters", "Sal Hagen"]
__email__ = "4cat@oilab.eu"

class Tokenise(BasicProcessor):
	"""
	Tokenize posts
	"""
	type = "tokenise-posts"  # job type ID
	category = "Text analysis"  # category
	title = "Tokenise"  # title displayed in UI
	description = "Tokenises post bodies, producing corpus data that may be used for further processing by e.g. NLP. The output is a serialized list of lists, with each post treated as a single document (so no sentence splitting)."  # description displayed in UI
	extension = "zip"  # extension of result file, used internally and in UI

	input = "csv:body"
	output = "zip"

	options = {
		"timeframe": {
			"type": UserInput.OPTION_CHOICE,
			"default": "all",
			"options": {"all": "Overall", "year": "Year", "month": "Month", "day": "Day"},
			"help": "Produce files per"
		},
		"tokenizer_type": {
			"type": UserInput.OPTION_CHOICE,
			"default": "twitter",
			"options": {"twitter": "nltk TweetTokenizer", "regular": "nltk word_tokenize"},
			"help": "Tokeniser",
			"tooltip": "TweetTokenizer is recommended for social media content, as it is optimised for informal language."
		},
		"language": {
			"type": UserInput.OPTION_CHOICE,
			"options": {language: language[0].upper() + language[1:] for language in SnowballStemmer.languages},
			"default": "english",
			"help": "Language"
		},
		"stem": {
			"type": UserInput.OPTION_TOGGLE,
			"default": False,
			"help": "Stem tokens (with SnowballStemmer)",
			"tooltip": "Stemming removes suffixes from words: 'running' becomes 'runn', 'bicycles' becomes 'bicycl', and so on."
		},
		"lemmatise": {
			"type": UserInput.OPTION_TOGGLE,
			"default": False,
			"help": "Lemmatise tokens (English only)",
			"tooltip": "Lemmatisation replaces inflections of a word with its root form: 'running' becomes 'run', 'bicycles' becomes 'bicycle', 'better' becomes 'good'."
		},
		"strip_symbols": {
			"type": UserInput.OPTION_TOGGLE,
			"default": True,
			"help": "Strip non-alphanumeric characters (e.g. punctuation)"
		},
		"accept_words": {
			"type": UserInput.OPTION_TEXT,
			"default": "",
			"help": "Always allow these words",
			"tooltip": "Separate with commas. These are not stemmed or lemmatised; provide variations yourself if needed."
		},
		"reject_words": {
			"type": UserInput.OPTION_TEXT,
			"default": "",
			"help": "Exclude these words",
			"tooltip": "Separate with commas. These are not stemmed or lemmatised; provide variations yourself if needed."
		},
		"filter": {
			"type": UserInput.OPTION_MULTI,
			"default": [],
			"options": {
				#"stopwords-terrier-english": "English stopwords (terrier, recommended)",
				"stopwords-iso-english": "English stopwords (stopwords-iso, recommended)",
				"stopwords-iso-dutch": "Dutch stopwords (stopwords-iso)",
				"stopwords-iso-all": "Multi-language stopwords (stopwords-iso)",
				#"wordlist-infochimps-english": "English word list (infochimps)",
				"wordlist-googlebooks-english": "English word list (Google One Million Books pre-2008 top unigrams, recommended)",
				"wordlist-cracklib-english": "English word list (cracklib)",
				"wordlist-opentaal-dutch": "Dutch word list (OpenTaal)",
				#"wordlist-unknown-dutch": "Dutch word list (unknown origin, larger than OpenTaal)"
			},
			"help": "Word lists to exclude (i.e. not tokenise). It is highly recommended to exclude stop words. Note that choosing more word lists increases processing time"
		}
	}

	def process(self):
		"""
		This takes a 4CAT results file as input, and outputs a number of files containing
		tokenised posts, grouped per time unit as specified in the parameters.
		"""
		self.dataset.update_status("Processing posts")

		link_regex = re.compile(r"https?://[^\s]+")
		symbol = re.compile(r"[^a-zA-Z0-9]")
		numbers = re.compile(r"\b[0-9]+\b")

		# Twitter tokenizer if indicated
		if self.parameters.get("tokenizer_type") == "twitter":
			tokenizer = TweetTokenizer(preserve_case=False)
			tweet_tokenizer = True
		else:
			tweet_tokenizer = False

		# load word filters - words to exclude from tokenisation
		word_filter = set()
		for wordlist in self.parameters.get("filter", self.options["filter"]["default"]):
			with open(config.PATH_ROOT + "/backend/assets/wordlists/%s.pb" % wordlist, "rb") as input:
				word_filter = set.union(word_filter, pickle.load(input))

		# Extend or limit the word filter with optionally added words
		# Remove accepted words from filter
		if self.parameters.get("accept_words", self.options["accept_words"]["default"]):
			accept_words = [str(word).strip() for word in self.parameters["accept_words"].split(",")]
			for accept_word in accept_words:
				if accept_word in word_filter:
					word_filter.remove(accept_word)

		# Add rejected words to filter
		if self.parameters.get("reject_words", self.options["reject_words"]["default"]):
			reject_words = [str(word).strip() for word in self.parameters["reject_words"].split(",")]
			word_filter.update(reject_words)

		# Create a regex for the word list which should be faster than iterating
		filter_regex = re.compile("|".join([re.escape(word) for word in word_filter if word]))

		language = self.parameters.get("language", "english")
		strip_symbols = self.parameters.get("strip_symbols", self.options["strip_symbols"]["default"])

		# initialise pre-processors if needed
		if self.parameters.get("stem", self.options["stem"]["default"]):
			stemmer = SnowballStemmer(language)

		if self.parameters.get("lemmatise", self.options["lemmatise"]["default"]):
			lemmatizer = WordNetLemmatizer()

		# this is how we'll keep track of the subsets of tokens
		subunits = {}
		current_subunit = ""

		# prepare staging area
		tmp_path = self.dataset.get_temporary_path()
		tmp_path.mkdir()

		# this needs to go outside the loop because we need to call it one last
		# time after the post loop has finished
		def save_subunit(subunit):
			"""
			Save token set to disk

			:param str subunit:  Subset ID
			"""
			with tmp_path.joinpath(subunit + ".pb").open("wb") as outputfile:
				pickle.dump(subunits[subunit], outputfile)

		# process posts
		self.dataset.update_status("Processing posts")
		timeframe = self.parameters.get("timeframe", self.options["timeframe"]["default"])

		for post in self.iterate_csv_items(self.source_file):

			# If it's empty, skip it!
			if not post.get("body", None):
				continue

			# determine what output unit this post belongs to
			if timeframe == "all":
				output = "overall"
			else:
				if "timestamp_unix" in post:
					try:
						timestamp = int(post["timestamp_unix"])
					except ValueError:
						timestamp = 0
				else:
					try:
						timestamp = int(datetime.datetime.strptime(post["timestamp"], "%Y-%m-%d %H:%M:%S").timestamp())
					except ValueError:
						timestamp = 0
				date = datetime.datetime.fromtimestamp(timestamp)
				if timeframe == "year":
					output = str(date.year)
				elif timeframe == "month":
					output = str(date.year) + "-" + str(date.month)
				else:
					output = str(date.year) + "-" + str(date.month) + "-" + str(date.day)

			# write each subunit to disk as it is done, to avoid
			# unnecessary RAM hogging
			if current_subunit and current_subunit != output:
				save_subunit(current_subunit)
				self.dataset.update_status("Processing posts (" + output + ")")
				subunits[current_subunit] = list()  # free up memory

			current_subunit = output

			# create a new list if we're starting a new subunit
			if output not in subunits:
				subunits[output] = list()

			# we're treating every post as one document.
			# this means it is not sensitive to sentences.
			post_tokens = []

			# clean up text and get tokens from it
			body = link_regex.sub("", post["body"])

			# Use differing tokenizers depending on the user input
			if tweet_tokenizer:
				tokens = tokenizer.tokenize(body)
			else:
				tokens = word_tokenize(body, language=language)

			# stem, lemmatise and save tokens that are not stopwords
			for token in tokens:
				token = token.lower()

				if strip_symbols:
					token = numbers.sub("", symbol.sub("", token))

				if not token: # Skip empty strings
					continue

				if filter_regex.fullmatch(token):
					continue

				if self.parameters["stem"]:
					token = stemmer.stem(token)

				if self.parameters["lemmatise"]:
					token = lemmatizer.lemmatize(token)

				# append tokens to the post's token list
				post_tokens.append(token)

			# append the post's tokens as a list within a larger list
			if post_tokens:
				subunits[output].append(post_tokens)

		# save the last subunit we worked on too
		save_subunit(current_subunit)

		# create zip of archive and delete temporary files and folder
		self.dataset.update_status("Compressing results into archive")
		with zipfile.ZipFile(self.dataset.get_results_path(), "w") as zip:
			for subunit in subunits:
				zip.write(tmp_path.joinpath(subunit + ".pb"), subunit + ".pb")
				tmp_path.joinpath(subunit + ".pb").unlink()

		# delete temporary folder
		shutil.rmtree(tmp_path)

		# done!
		self.dataset.update_status("Finished")
		self.dataset.finish(len(subunits))