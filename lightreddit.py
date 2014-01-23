#!/usr/bin/python3

import time
import os
import urllib.request
import urllib.parse
import http.cookiejar
import json

class RedditSession():
	"""
	Usage:
		First, create a RedditSession object. Then the following public methods are available:

		get_comments()
		get_submissions()
		get_thread()
		submit()

		There is no login() method. Logging in is done lazily, as needed.
	"""
	urls = {
		"comments":		{"url":"r/$r/comments.json",		"auth":False,	"args":{},	"get_only":False},
		"submissions":	{"url":"r/$r/new.json",				"auth":False,	"args":{},	"get_only":False},
		"thread":		{"url":"comments/$r.json",			"auth":False,	"args":{},	"get_only":False},
		"morechildren":{"url":"api/morechildren.json",	"auth":False,	"args":{"api_type":"json"},	"get_only":False},

		"report":		{"url":"api/report.json",			"auth":True,	"args":{},	"get_only":False},
		"remove":		{"url":"api/remove.json",			"auth":True,	"args":{},	"get_only":False},
		"reply":			{"url":"api/comment.json",			"auth":True,	"args":{"api_type":"json"},	"get_only":False},
		"distinguish":	{"url":"api/distinguish.json",	"auth":True,	"args":{},	"get_only":False},
		"submit":		{"url":"api/submit.json",			"auth":True,	"args":{},	"get_only":False},

		"modlog":		{"url":"r/$r/about/log.json",		"auth":True,	"args":{},	"get_only":True},
		"flairlist":	{"url":"r/$r/api/flairlist.json","auth":False,	"args":{},	"get_only":False},

		"overview":		{"url":"user/$r/overview.json",	"auth":False,	"args":{},	"get_only":False},
		"u_comments":	{"url":"user/$r/comments.json",	"auth":False,	"args":{},	"get_only":False},
		"u_submitted":	{"url":"user/$r/submitted.json",	"auth":False,	"args":{},	"get_only":False},
		"inbox":			{"url":"message/inbox.json",		"auth":True,	"args":{},	"get_only":True},
		"sent":			{"url":"message/sent.json",		"auth":True,	"args":{},	"get_only":True},
		"modmail":		{"url":"r/$r/message/moderator/inbox.json","auth":True,"args":{},	"get_only":True},
		"message":		{"url":"message/messages/$r.json","auth":True,"args":{},	"get_only":True},
		"message_m":	{"url":"r/$r.json",					"auth":True,	"args":{},	"get_only":True},	#TODO temporary workaround for reddit.com bug

		"compose":		{"url":"api/compose.json",			"auth":True,	"args":{"api_type":"json"},	"get_only":False},

		"mysubs":		{"url":"subreddits/mine/subscriber.json",	"auth":True,	"args":{},	"get_only":True},
		"mymods":		{"url":"subreddits/mine/moderator.json",	"auth":True,	"args":{},	"get_only":True},

		"banned":		{"url":"r/$r/about/banned.json",	"auth":True,	"args":{},	"get_only":True},
		"ban":			{"url":"api/friend",					"auth":True,	"args":{"type":"banned"},	"get_only":False},
		"unban":			{"url":"api/unfriend",				"auth":True,	"args":{"type":"banned"},	"get_only":False},
		"about":			{"url":"r/$r/about.json",			"auth":False,	"args":{},	"get_only":False},
		"edit":			{"url":"r/$r/about/edit.json",	"auth":True,	"args":{},	"get_only":True},
		"site_admin":	{"url":"api/site_admin",			"auth":True,	"args":{"api_type":"json"},	"get_only":False},

		"wiki_write":	{"url":"r/$r/api/wiki/edit",		"auth":True,	"args":{},	"get_only":False}
	}

	_listing_batch = 100			#fetch this many listings at a time
	_listing_limit = 1500		#fetch this many listings total
	_morechildren_limit = 2		#fetch this many hidden children at a time	#TODO start this higher and cut it by half (and restart action) every time a t1__ error pops up
		#TODO or maybe just leave things clumpted together the way they appear in the Mores

	def __init__(self, u, p, agent):
		self.next_req_time = time.time() + 2
		self.uh = None
		self.user = u
		self.passwd = p
		self.user_agent = agent + " [python-lightreddit]"

	def _login(self):
		"""Log in to reddit. Use the stored cookie if possible."""
		cookie_path = "/tmp/lightreddit_cookie_"+str(hash(self.user)%10000)	#CONFIGURE HERE
		open(cookie_path, "a").close()	#create the file if it doesn't exist
		os.chmod(cookie_path, 0o600)		#set appropriate permissions before we use it for anything

		cj = http.cookiejar.LWPCookieJar(cookie_path)
		urllib.request.install_opener(urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj)))

		try:
			cj.load()
		except http.cookiejar.LoadError:
			pass		#we don't care if it fails. We're going to fetch a new cookie if we can't find reddit_session, anyway.
		except IOError:
			pass
		if "reddit_session" not in [x.name for x in list(cj)]:	#we don't have a session cookie
			if not self.user or not self.passwd:
				raise RuntimeError("no username or password set")
			y = self.req_raw("https://pay.reddit.com/api/login", {"passwd":self.passwd, "rem":True, "user":self.user})
			#y = self.req_raw("http://www.reddit.com/api/login", {"passwd":self.passwd, "rem":True, "user":self.user})
		#now we have a session cookie, either new or from cj
		headers = []

		y = self.req_raw("http://www.reddit.com/api/me.json", headers=headers)
		z = json.loads(y.read().decode("utf8"))
		self.uh = z["data"]["modhash"]
		#["has_mail", "has_mod_mail"]
		cj.save(ignore_discard=True, ignore_expires=True)

	def req(self, url_name, rname="", args=None, get_args=None):
		"""Build a request, send it through the dispatcher, and return the response body"""
		u = RedditSession.urls[url_name]
		url = "http://www.reddit.com/%s" % (u["url"])
		url = url.replace("$r", rname)
		if get_args is not None:
			url += "?" + "&".join(["%s=%s" % (x[0], x[1]) for x in get_args.items()])
		if args is not None:
			args = dict(u["args"], **args)	#later ones override in case of collision with defaults
		if u["auth"]:
			if self.uh is None:
				self._login()
			if args is None:
				args = {}
			args["uh"] = self.uh
		if u["get_only"]:
			args = {}
		return json.loads(self.req_raw(url, args).read().decode("utf8"))

	def req_raw(self, url, args=None, headers=None):
		"""Dispatch an actual request to reddit.com and return the Response object"""
		if headers is None:	headers = []
		if args is None:		args = {}
		x = urllib.request.Request(url, data=(urllib.parse.urlencode(args).encode("ascii") if args else None))

		x.add_header("User-Agent", self.user_agent)	#FIXME ensure the RHS is in quotes, because some characters are not valid naked on the RHS of HTTP headers
		for h in headers:
			x.add_header(h[0], h[1])
		delay = self.next_req_time - time.time()
		if delay > 0:
			#print("have to sleep for %f" % (delay))
			time.sleep(delay)
		#print("%f req %s \"%s\" %s %s" % (time.time(), x.get_method(), x.get_full_url(), x.header_items(), x.get_data()))
		y = urllib.request.urlopen(x)
		self.next_req_time = time.time() + 2
		if y.status != 200:	#FIXME reddit.com still returns 200 when there was a higher-level error
			print("%s: %s" % (y.status, y.reason))
		return y

	def get_comments(self, rname, start=None):
		"""Get recent comments from rname and return a list of Comment objects
		If start is set, work forward from just after there to the front. Otherwise, get the last RedditSession._listing_limit."""
		if start:
			return self._get_listing("comments", rname, start)
		else:
			return self._get_listing_backwards("comments", rname)

	def get_submissions(self, rname, start=None):
		"""Get recent submissions from rname
		If start is set, work forward from just after there to the front. Otherwise, get the last RedditSession._listing_limit."""
		if start:
			return self._get_listing("submissions", rname, start)
		else:
			return self._get_listing_backwards("submissions", rname)

	def get_user_overview(self, uname, start=None, limit=0):
		"""Get recent comments and submissions by user
		If start is set, work forward from just after there to the front. Otherwise, get the last RedditSession._listing_limit."""
		try:
			if start:	return self._get_listing("overview", uname, start)
			else:			return self._get_listing_backwards("overview", uname, limit=limit)
		except urllib.error.HTTPError as e:
			if e.code == 404:	raise NoSuchUserException()

	def get_thread(self, id):
		"""Get a thread (submission and comments) by id (without the 't3_')"""
		items = self.req("thread", id, get_args={"limit":RedditSession._listing_batch, "api_type":"json"})

		submission = self._thing_factory(items[0]["data"]["children"][0])
		comments = self._listing_to_comment_array(items[1]["data"]["children"])
		self._get_more_comments(comments, first=True)

		return RedditThread(self, submission, comments)

	def get_user(self, name):
		"""Creates a RedditUser object"""
		return RedditUser(self, name)

	def _listing_to_comment_array(self, a):#, depth=0):	#DEBUG depth
		coms = []
		for c in a:
			t = self._thing_factory(c)
			if t.__class__ == RedditMore:
				print(t)
			if t.__class__ == RedditComment:
				if c["data"]["replies"] != "" and c["data"]["replies"] != None:
					t.replies = self._listing_to_comment_array(c["data"]["replies"]["data"]["children"])#, depth+1)
			coms.append(t)
		return coms

	def _get_more_comments(self, root, to_get=[], first=False):
		"""Get ommitted comments recursively.
		root is the array of top-level comments (which contain their own children).
		This function modifies root in-place."""
		#recurse through the comments and build a list (to_get) of the omitted ones
		for c in root:
			if c.__class__ == RedditMore:
				to_get += c.children
				root.remove(c)
			elif c.__class__ == RedditComment:
				self._get_more_comments(c.replies, to_get)
		if first:
			to_add = []
			while True:
				for t in to_add:	#get the leftovers. to_add is empty first time through.
					if t.__class__ == RedditMore:
						to_get += t.children
						to_add.remove(t)
				#fetch the comments in to_get
				link_id = root[0].link_id
				for chunk in [to_get[i:i+RedditSession._morechildren_limit] for i in range(0, len(to_get), RedditSession._morechildren_limit)]:
					t = self.req("morechildren", "", args={"children": ",".join(chunk), "link_id": link_id})
					for a in t["json"]["data"]["things"]:
						if a["data"]["id"] == "_":
							print("ERROR")
						to_add.append(self._thing_factory(a))
				self._add_more_comments(root, to_add, first=True)
				to_get = []	#blank the list for the next iteration
				if len(to_add) == 0:
					break

	def _add_more_comments(self, root, to_add, first=False):
		"""Add newly-fetched comments to a tree"""
		if first:
			#first handle top-level comments. they have parent_id == thread's t3id
			for t in to_add:
				if t.__class__ == RedditComment:
					if t.parent_id == t.link_id:
						root.append(t)
						to_add.remove(t)
				self._add_more_comments(root.replies, to_add)
		#now handle all the other comments we fetched
		for c in root:
			for t in to_add:
				if t.__class__ == RedditComment:
					if t.parent_id == c.name:
						c.replies.append(t)
						to_add.remove(t)
			self._add_more_comments(c.replies, to_add)

	def get_modlog(self, rname, start=None):
		"""Get the moderation log for a given subreddit
		If start is set, work forward from there to the front. Otherwise, get the last RedditSession._listing_limit."""
		if start:	return self._get_listing("modlog", rname, start)
		else:			return self._get_listing_backwards("modlog", rname)

	def get_inbox(self, start=None):
		"""Get messages from inbox
		If start is set, work forward from there to the front. Otherwise, get the last RedditSession._listing_limit."""
		if start:	return self._get_listing("inbox", "", start)
		else:			return self._get_listing_backwards("inbox")

	def get_sent(self, start=None):
		"""Get sent messages
		If start is set, work forward from there to the front. Otherwise, get the last RedditSession._listing_limit."""
		if start:	return self._get_listing("sent", "", start)
		else:			return self._get_listing_backwards("sent")

	def message(self, user, subject, text):
		"""Send a private message to user (or modmail, if user is #subredditname)."""
		self.session.req("compose", args={"to":user, "subject":subject, "text":text})

	def get_user_comments(self, uname="", start=None, limit=0):
		"""Get comments by a user
		If start is set, work forward from there to the front. Otherwise, get the last RedditSession._listing_limit."""
		if not uname:
			if not self.user:
				raise RuntimeError("no username or password set")
			uname = self.user
		try:
			if start:	return self._get_listing("u_comments", uname, start)
			else:			return self._get_listing_backwards("u_comments", uname, limit=limit)
		except urllib.error.HTTPError as e:
			if e.code == 404:	raise NoSuchUserException()

	def get_user_submitted(self, uname="", start=None, limit=0):
		"""Get submissions by a user
		If start is set, work forward from there to the front. Otherwise, get the last RedditSession._listing_limit."""
		if not uname:
			if not self.user:
				raise RuntimeError("no username or password set")
			uname = self.user
		try:
			if start:	return self._get_listing("u_submitted", uname, start)
			else:			return self._get_listing_backwards("u_submitted", uname, limit=limit)
		except urllib.error.HTTPError as e:
			if e.code == 404:	raise NoSuchUserException()

	def get_flairlist(self, rname):
		"""Get a subreddit's flairlist"""
		a = []
		n = ""
		done = False
		while True:
			items = self.req("flairlist", rname, get_args={"after":n, "limit":1000})
			try:
				n = items["next"]
			except KeyError:
				done = True
			a.extend(items["users"])
			if done:
				break
		return a

	def get_modmail(self, rname, start=None, limit=0):
		"""Get modmail for a subreddit
		If start is set, work forward from there to the front. Otherwise, get the last RedditSession._listing_limit."""
		if start:	a = self._get_listing("modmail", rname, start)
		else:			a = self._get_listing_backwards("modmail", rname, limit=limit)
		return sorted(a, key=lambda x: x.replies[-1].created_utc if len(x.replies) > 0 else x.created_utc)	#modmail is sorted by date of most recent reply

	def get_message(self, mid):
		"""Get a specific message. It's still a listing, even though there's only one item."""
		listing = self._get_listing("message", mid, "")
		if len(listing) > 1:
			raise RuntimeError("get_message(%s) returned a list longer than 1 element" % (mid))
		return listing[0]

	def get_message_modmail(self, mid, rname):
		"""Get a specific modmail message. This is a workaround for a reddit.com bug that sometimes prevents get_message() from returning all replies of a modmail thread."""
		listing = self._get_listing("message_m", "%s/message/messages/%s" % (rname, mid), "")
		if len(listing) > 1:
			raise RuntimeError("get_message_modmail(%s) returned a list longer than 1 element: %s" % (mid, listing))
		return listing[0]

	def get_subreddits_subscribed(self):
		"""Get list of subreddits subscribed to"""
		return self._get_listing_backwards("mysubs")

	def get_subreddits_mod(self):
		"""Get list of subreddits moderated"""
		return self._get_listing_backwards("mymods")

	def get_subreddit_about(self, rname):
		"""Get subreddit description (sidebar)"""
		return self.req("about", rname)

	def get_subreddit_settings(self, rname):
		"""Get subreddit settings (suitable for passing to site_admin)"""
		return self.req("edit", rname)["data"]

	def set_subreddit_settings(self, rname, s):
		"""Set subreddit settings"""
		keys = ["allow_top", "comment_score_hide_mins", "css_on_cname", "description", "exclude_banned_modqueue", "header-title", "lang", "link_type", "name", "over_18", "public_description", "public_traffic", "show_cname_sidebar", "show_media", "spam_comments", "spam_links", "spam_selfposts", "sr", "submit_link_label", "submit_text", "submit_text_label", "title", "type", "wiki_edit_age", "wiki_edit_karma", "wikimode"]

		s["allow_top"] = s["default_set"]
		del(s["default_set"])
		s["css_on_cname"] = s["domain_css"]
		del(s["domain_css"])
		s["header-title"] = s["header_hover_text"]
		del(s["header_hover_text"])
		s["lang"] = s["language"]
		del(s["language"])
		s["link_type"] = s["content_options"]
		del(s["content_options"])
		s["name"] = rname
		s["show_cname_sidebar"] = s["domain_sidebar"]
		del(s["domain_sidebar"])
		s["sr"] = s["subreddit_id"]
		del(s["subreddit_id"])
		s["type"] = s["subreddit_type"]
		del(s["subreddit_type"])

		for k in keys:
			if k not in s.keys():
				raise BadSettingsException("'%s' not provided" % (k))
		for k in s.keys():
			if s[k] == None:
				s[k] = ""
		#if len(keys) != len(s.keys()):
		#	raise BadSettingsException("Wrong number of arguments provided")
		return self.req("site_admin", args=s)

	def get_banned(self, rname, start=None):
		"""Get banned users for a subreddit"""
		items = self.req("banned", rname)

		a = []
		for b in items["data"]["children"]:
			b["subreddit"] = rname
			a.append(RedditBan(self, b))
		return a

	def _get_listing(self, url, rname, start, sort=None):
		"""Get recent items from a listing
		If start is set, work forward from just after there to the front. Otherwise, get the last RedditSession._listing_limit."""
		a = []
		n = start if start is not None else ""		#requesting "before=t3_" has the effect of not even including the request parameter
		while True:
			items = self.req(url, rname, get_args={"limit":RedditSession._listing_batch,"before":n})
			if len(items["data"]["children"]) == 0:	#maybe there's nothing to get, or maybe our 'before=' thing disappeared from reddit and we're missing data
				print("DEBUG: switching to backwards mode with end==%s" % (start))
				return self._get_listing_backwards(url, rname, start) #to be safe, we'll start grabbing things from the front working backwards until we overlap the tid of what we thought was the latest
			for item in reversed(items["data"]["children"]):
				a.append(self._thing_factory(item))
			if start and len(items["data"]["children"]) == RedditSession._listing_batch:	#maybe there were more than RedditSession._listing_batch items, so try to get more
				n = a[-1].name
			else:
				break
			if len(a) > min(RedditSession._listing_limit, 2000):	#safety stop at 2000
				break

		if sort:
			return sorted(a, key=lambda x: getattr(x, sort))
		return a

	def _get_listing_backwards(self, url, rname="", end="", sort=None, limit=0):
		"""Get recent items to a listing
		If start is set, work backward from front to there. Otherwise, get the last RedditSession._listing_limit."""
		try:
			end_int = int(end[3:], 36) if end != "" else 0
		except ValueError:
			end_int = 0	#something that doesn't have an id36, like Modlog. In that case, always fetch to the max limit
		a = []
		n = ""		#start from the most recent every time
		batch = min(RedditSession._listing_batch, limit) if limit > 0 else RedditSession._listing_batch
		while True:
			items = self.req(url, rname, get_args={"limit":batch,"after":n})	#get RedditSession._listing_batch every time and manually find the stopping point later
			passed_end = False
			for item in items["data"]["children"]:
				try:
					if int(item["data"]["id"], 36) > end_int:	#haven't reach the end yet
						a.append(self._thing_factory(item))
				except ValueError:
						a.append(self._thing_factory(item))	#something that can't be compared, like Modlog. In that case, always fetch to the max limit
				else:
					passed_end = True			#note that we can't break early because reddit might not return the results in tid order. maybe. let's be safe and process the whole batch.
			if len(items["data"]["children"]) == 0 or passed_end:
				break
			if len(a) > min(RedditSession._listing_limit, 2000) or (limit != 0 and len(a) >= limit):	#safety stop at 2000
				break
			n = items["data"]["after"]
			if n == None:
				break
		if sort:
			return sorted(a, key=lambda x: getattr(x, sort))
		return list(reversed(a))

	def submit(self, rname, title, text):
		"""Submit a new post to rname"""
		self.req("submit", args={"sr":rname, "kind":"self", "title":title, "text":text})

	def ban(self, rname, user, note):
		"""Ban user from rname with reason note"""
		self.req("ban", args={"r":rname, "name":user, "note":note})

	def unban(self, rname, user):
		"""Unban user from rname"""
		self.req("unban", args={"r":rname, "name":user})

	def wiki_write(self, rname, page, content, reason):
		"""Write content (in reddit markdown) to rname's wiki page with optional reason. All exsting content is overwritten."""
		self.req("wiki_write", rname, args={"page":page, "content":content, "reason":reason})

	def _thing_factory(self, x):
		"""Create the proper object for a thing"""
		if x["kind"] == "t1":
			return RedditComment(self, x)
		if x["kind"] == "t3":
			return RedditSubmission(self, x)
		if x["kind"] == "t4":
			return RedditMessage(self, x)
		if x["kind"] == "t5":
			return RedditSubreddit(self, x)
		if x["kind"] == "more":
			return RedditMore(self, x)
		if x["kind"] == "modaction":
			return RedditModaction(self, x)
		if x["kind"] == "wikipage":
			return RedditWikipage(self, x)
		else:
			print("DEBUG: unknown thing type: %s" % (x))

class RedditThing:
	"""A comment or submission. Could also be a message in the future, but that's unused now."""

	def __init__(self, session, data):
		#print("handling a %s" % (self.__class__))
		if self.__class__ == RedditThing:
			raise NotImplementedError("This is an abstract class.")
		self.session = session
		self.kind = data["kind"]
		for k in type(self).fields:
			try:
				setattr(self, k, data["data"][k])
			except KeyError:
				pass #we don't care. If reddit.com didn't send us a key, then we're not supposed to have it.
		try:
			for k in type(self).user_fields:
				try:
					setattr(self, k, RedditUser(session, data["data"][k]))
				except KeyError:
					pass
		except AttributeError:
			pass
		#self.int_id = int(self.id,36)
		self.raw = data

	def reply(self, text, distinguish=False):
		"""Reply to the thing"""
		response = self.session.req("reply", args={"thing_id":self.name, "text":text})
		new_thing = RedditComment(self.session, response["json"]["data"]["things"][0])
		if new_thing == None:	#the response didn't tell us what the new thing is, so it probably didn't submit successfully
			raise RuntimeError #FIXME make the error more specific
		if distinguish:
			new_thing.distinguish()

	def distinguish(self, distinguish=True):
		"""Distinguish or undistinguish a thing"""
		self.session.req("distinguish", args={"id":self.name, "how":("yes" if distinguish else "no")})

	def remove(self):
		"""Remove the thing"""
		self.session.req("remove", args={"id":self.name, "spam":False})

	def report(self):
		"""Report the thing to the moderators"""
		self.session.req("report", args={"id":self.name})

class RedditSubmission(RedditThing):
	"""A submission (link or self-post), without comments"""

	fields = ["name", "domain", "subreddit", "selftext", "title", "link_flair_css_class", "is_self", "permalink", "url", "created_utc", "num_reports"]
	user_fields = ["author", "banned_by", "approved_by"]

	def __str__(self):
		return "<RedditSubmission(%s, %s, %s, %s)>" % (self.name, self.author, self.domain, self.title)

class RedditComment(RedditThing):
	"""A single comment"""

	fields = ["name", "body", "edited", "created_utc", "num_reports", "subreddit", "link_id", "id", "parent_id"]
	user_fields = ["author", "banned_by", "approved_by"]

	def __init__(self, session, data):
		super(RedditComment, self).__init__(session, data)
		self.replies = []

	def __str__(self):
		return "<RedditComment(%s, %s, %s)>" % (self.name, self.author, "%s...(%d)" % (self.body[:100].replace("\n", "\\n"), len(self.body)))

class RedditMore(RedditThing):
	"""A 'more' object"""

	fields = ["count", "parent_id", "id", "children"]

	def __str__(self):
		return "<RedditMore(%s, parent=%s, %s)>" % (self.id, self.parent_id, self.children)

class RedditThread(RedditThing):
	"""An entire thread, submission and comments"""

	def __init__(self, session, subm, coms):
		self.session = session
		self.submission = subm
		self.comments = coms

	def __str__(self):
		return "<RedditThread(%s, %s)>" % (self.submission, self.comments)

class RedditModaction(RedditThing):
	"""A 'more' object"""

	fields = ["description", "id", "created_utc", "subreddit", "details", "action", "target_fullname"]
	user_fields = ["mod"]

	def __init__(self, session, data):
		super(RedditModaction, self).__init__(session, data)
		self.name = self.id	#for convenience in _get_listing

	def __str__(self):
		return "<RedditModaction(%s, %s, %s, %s)>" % (self.id, self.subreddit, self.mod, self.action)

class RedditMessage(RedditThing):
	"""A message object (inbox or sent)"""

	fields = ["body", "was_comment", "first_message", "name", "first_message_name", "created_utc", "body_html", "subreddit", "parent_id", "context", "subject"]
	user_fields = ["dest", "author"]

	def __init__(self, session, data):
		super(RedditMessage, self).__init__(session, data)
		if data["data"]["replies"]:	#TODO handle "before" and "after"
			self.replies = [session._thing_factory(x) for x in data["data"]["replies"]["data"]["children"]]
		else:
			self.replies = []

	def __str__(self):
		return "<RedditMessage(%s, %s, %s, %s)>" % (self.name, self.author, self.dest, "%s...(%d)" % (self.body[:100].replace("\n", "\\n"), len(self.body)))

class RedditSubreddit(RedditThing):
	"""A subreddit object"""

	fields = ["header_title", "header_img", "title", "name", "created_utc", "accounts_active", "over18", "subscribers", "public_description", "display_name", "description"]

	def ban(self, user, note):
		"""Ban user from subreddit with reason note"""
		self.req("ban", args={"r":self.name, "name":user, "note":note})

	def unban(self, user):
		"""Unban user from subreddit"""
		self.req("unban", args={"r":self.name, "name":user})

	def __str__(self):
		return "<RedditSubreddit(%s, %s)>" % (self.name, self.display_name)

class RedditBan(RedditThing):
	"""A ban object"""

	fields = ["name", "note", "subreddit"]	#note we do something weird in the constructor because these objects have field names inconsistent with the rest of reddit
	user_fields = ["user"]

	def __init__(self, session, data):
		super(RedditBan, self).__init__(session, {"kind":"ban", "data":{"name":data["id"], "user":data["name"], "note":data["note"], "subreddit":data["subreddit"]}})

	def __str__(self):
		return "<RedditBan(%s, %s, %s)>" % (self.subreddit, self.user, self.note)

class RedditUser:
	"""A redditor object. Note that this can sometimes be "#subreddit", in which case fake_user will be true."""
	def __init__(self, session, name):
		self.session = session
		self.kind = "t2"
		self.name = name
		if name != None and name[0] == "#":
			self.fake_user = True
		else:
			self.fake_user = False

	def message(self, subject, text):
		"""Send a private message to user (or modmail, if user is #subredditname)."""
		self.session.req("compose", args={"to":self.name, "subject":subject, "text":text})

	def ban(self, rname, note):
		"""Ban user from rname with reason note"""
		self.session.req("ban", args={"r":rname, "name":self.name, "note":note})

	def unban(self, rname):
		"""Unban user from rname"""
		self.session.req("unban", args={"r":rname, "name":self.name})

	def __str__(self):
		return "<RedditUser(%s)>" % (self.name)

class RedditWikipage(RedditThing):
	"""A revision of a wiki page"""

	fields = ["may_revise", "revision_date", "content_html", "content_md"]

	def __init__(self, session, data):
		super(RedditModaction, self).__init__(session, data)
		self.user = RedditUser(session, data["revision_by"]["data"]["name"])

	def __str__(self):
		return "<RedditWikipage(%s)>" % (self.content_md[:30])

class NoSuchUserException(Exception):
	"""Also shadowbanned users"""
	pass

class BadSettingsException(Exception):
	"""The library raises this before attempting to call site_admin with wonky-looking parameters"""
	pass
