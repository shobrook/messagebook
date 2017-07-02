from bson.errors import InvalidId
from bson.objectid import ObjectId
from flask import Flask, jsonify, request, json, abort
from flask_pymongo import PyMongo


# GETTING

def get_all_content_recursive(mongo, folder):

	if folder is None:
		return

	# Gathers all conversations in the folder
	conversation_list = []
	for conversation_id in folder["conversations"]:
		conversation = mongo.db.conversations.find_one({"_id": conversation_id})
		conversation_list.append({"name": conversation["name"], "messages": conversation["messages"]})

	# Recursively traverses subfolders
	children_list = []
	for subfolder in folder["children"]:
		subfolder_id = mongo.db.folders.find_one({"_id": subfolder})
		children_list.append(get_all_content_recursive(mongo, subfolder_id))

	return {"name": folder["name"], "conversations": conversation_list, "children": children_list}

# TODO: Make this not atrociously inefficient
def get_all_content(mongo, request_json):
	user = mongo.db.users.find_one({"authToken": request_json["authToken"]})

	# TODO: Add "root" as a property for folders so that we can rename the top-level folder
	root_folder = mongo.db.folders.find_one({"user_id": user["_id"], "root": True})

	if root_folder:
		return [get_all_content_recursive(mongo, root_folder)]

	abort(500, "get_all_content(): root folder for user " + user["email"] + " doesn't exist")
	return None

def get_folders(mongo, request_json):
	user = mongo.db.users.find_one({"authToken": request_json["authToken"]})
	folder_name_list = []
	for folder in mongo.db.folders.find({"user_id": user["_id"]}):
		folder_name_list.append(folder["name"])
	return folder_name_list

def get_database(mongo):
	users = []
	folders = []
	conversations = []

	for u in mongo.db.users.find():
		users.append({
			"_id": str(u["_id"]),
			"authToken": u["authToken"],
			"email": u["email"],
			"password": u["password"],
			"root": str(u["root"])
		})
	for f in mongo.db.folders.find():
		folders.append({
			"_id": str(f["_id"]),
			"user_id": str(f["user_id"]),
			"name": f["name"],
			"children": f["children"],
			"conversations": f["conversations"]
		})
	for c in mongo.db.conversations.find():
		conversations.append({
			"_id": str(c["_id"]),
			"name": c["name"],
			"messages": c["messages"]
		})

	return users, folders, conversations



# ADDING

def add_user(mongo, request_json):
	root_id = mongo.db.folders.insert({
		"name": "Everything",
		"root": True,
		"children": [],
		"conversations": []
	})
	user_id = mongo.db.users.insert({
		"authToken": [request_json["authToken"]],
		"email": request_json["email"],
		"password": request_json["password"],
		"root": root_id
	})
	mongo.db.folders.update_one({
		"_id": root_id},
		{"$set": {"user_id": ObjectId(str(user_id))}
	}, upsert=False)

	return str(user_id)

# Adds folder under a specified parent folder
# TODO: Check that we don't add duplicate folders
def add_folder(mongo, request_json):
	user = mongo.db.users.find_one({"authToken": request_json["authToken"]})

	folder_id = mongo.db.folders.insert({
		"name": request_json["name"],
		"root": False,
		"children": [],
		"conversations": [],
		"user_id": ObjectId(str(user["_id"]))
	})
	parentFolder = mongo.db.folders.update_one({
		"name": request_json["parent"],
		"user_id": ObjectId(str(user["_id"]))},
		{"$push": {"children": ObjectId(str(folder_id))}
	}, True)

	return str(folder_id)

def add_conversation(mongo, request_json):
	user = mongo.db.users.find_one({"authToken": request_json["authToken"]})
	folder = mongo.db.folders.find_one({"name": request_json["folder"], "user_id": ObjectId(str(user["_id"]))})
	convo = {
		"name": request_json["name"],
		"messages": request_json["messages"],
		"folder": folder["_id"]
	}
	convo_id = mongo.db.conversations.insert(convo)
	mongo.db.folders.update_one({
		"_id": folder["_id"]},
		{"$push": {"conversations": ObjectId(str(convo_id))}
	}, True)

	return str(convo_id)



# EDITING

def rename_folder(mongo, request_json):
	mongo.db.folders.update_one({
		"name": request_json["name"]},
		{"$set": {"name": request_json["newName"]}
	}, True)
	return True

def update_user(mongo, request_json):
	user = mongo.db.users.find_one({
		"email": request_json["email"],
		"password": request_json["password"]
	})
	if request_json["authToken"] in user["authToken"]:
		return False
	else:
		mongo.db.users.update_one({
			"_id": ObjectId(str(user["_id"]))},
			{"$push": {"authToken": request_json["authToken"]}
		}, True)
	return True



# DELETING

# TODO: Also remove from parent folder's conversations list
def delete_conversation(mongo, request_json):
	for conversation in mongo.db.conversations.find({"name": request_json["name"]}):
		mongo.db.conversations.remove(conversation["_id"])
	return True

# TODO: Make this not horribly inefficient
# TODO: Fix duplicate parent-child bug
def delete_folder(mongo, request_json):
	for folder in mongo.db.folders.find({"name": request_json["parent"]}):
		for subfolder_id in folder["children"]:
			subfolder = mongo.db.folders.find_one({"_id": subfolder_id})
			if subfolder["name"] == request_json["name"]:
				# Don't delete the root folder
				if subfolder["root"]:
					return
				mongo.db.folders.remove(subfolder_id)
				# folder["children"].remove(subfolder_id)
				# print("folder['_id']: " + str(folder["_id"]))
				# print("subfolder_id: " + str(subfolder_id))
				mongo.db.folders.update({"_id": folder["_id"]}, {"$pull": {"children": subfolder_id}})
				return
	return True



# MISCELLANIOUS

def validate_user(mongo, request_json):
	if not "password" in request_json:
		if mongo.db.users.find({"email": request_json["email"]}) != []:
				return False
		return True

	if mongo.db.users.find({"email": request_json["email"], "password": request.json["password"]}) != []:
			return True
	return False



if __name__ == "__main__":

	AUTH_ID = u'ya29.Glx6BP2MHLV0xcegcsPzy378uZmJo4kgygGturW8jrGCC80ygI8BcxhezpQhAXFjd4pK6Z1sDdHWq8N1P04DSh2H1zOJ18uvLyNAX3u50fCEdPufK7R5eXIkiyUP7g'

	import pprint
	pp = pprint.PrettyPrinter(indent=2)

	app = Flask(__name__)
	app.config['MONGO_DBNAME'] = 'tabberdb'
	app.config['MONGO_URI'] = 'mongodb://localhost:27017/tabberdb'
	mongo = PyMongo(app)

	with app.app_context():
		# request_json = {u'authToken': AUTH_ID}
		# pp.pprint(get_all_content(mongo, request_json))

		request_json = {u'parent': 'root', u'name': 'New Folder', u'authToken': AUTH_ID}
		print("Added folder: " + add_folder(mongo, request_json))

		# request_json = {"name": "New Folder", "newName": "Renamed Folder", u'authToken': AUTH_ID}
		# print("Renamed folder status: " + str(rename_folder(mongo, request_json)

		# request_json = {"name": "Works for me", u'authToken': AUTH_ID}
		# print("Removed conversation status: " + str(delete_conversation(mongo, request_json)))

		request_json = {"name": "New Folder", "parent": "root", u'authToken': AUTH_ID}
		print("Removed folder status: " + str(delete_folder(mongo, request_json)))
