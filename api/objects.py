import os
import zipfile
from datetime import datetime
from api.client import Client
from api.helper import Singleton
import api.parser as parser

#
# OBJECTS
# See also https://github.com/splitbrain/ReMarkableAPI/wiki/Storage
#
class ItemFactory(metaclass=Singleton):
    

    def __init__(self,):
        self.rm_client = Client()
        self.root = None


    def get_item(self, uuid):
        if self.root is None:
            self.get_root()

        return self._get_item_rec(self.root, uuid)
        

    def _get_item_rec(self, item, uuid):
        if item.uuid == uuid:
            return item
        
        for child in item.children:
            found = self._get_item_rec(child, uuid)
            if found != None:
                return found

        return None


    def get_root(self):
        entries = self.rm_client.list_metadata()
        self.root = self._create_tree(entries)
        return self.root


    def _create_tree(self, entries):

        lookup_table = {}
        for i in range(len(entries)):
            lookup_table[entries[i]["ID"]] = i

        # Create a dummy root object where everything starts
        root = Collection(None, None)
        items = {
            "": root
        }

        for i in range(len(entries)):
            self._create_tree_recursive(i, entries, items, lookup_table)

        return root


    def _create_tree_recursive(self, i, entries, items, lookup_table):
        entry = entries[i]
        parent_uuid = entry["Parent"]

        if i < 0 or len(entries) <= 0 or entry["ID"] in items:
            return

        if not parent_uuid in items:
            if not parent_uuid in lookup_table:
                print("(Warning) No parent for item %s" % entry["VissibleName"])
                parent_uuid = ""
            else:
                parent_id = lookup_table[parent_uuid]
                self._create_tree_recursive(parent_id, entries, items, lookup_table)

        parent = items[parent_uuid]
        new_object = self._item_factory(entry, parent)
        items[new_object.uuid] = new_object
            

    def _item_factory(self, entry, parent):
        if entry["Type"] == "CollectionType":
            new_object = Collection(entry, parent)

        elif entry["Type"] == "DocumentType":
            new_object = Document(entry, parent)

        else: 
            raise Exception("Unknown type %s" % entry["Type"])
        
        parent.add_child(new_object)
        return new_object


class Item(object):
    def __init__(self, entry, parent=None):
        self.children = []
        is_root = entry is None
        if is_root:
            self.uuid = ""
            self.is_document = False
            self.parent = None
            return 

        self.rm_client = Client()
        self.parent = parent
        self.uuid = entry["ID"]
        self.version = entry["Version"]
        self.name = entry["VissibleName"]
        self.is_document = entry["Type"] == "DocumentType"
        self.success = entry["Success"]
        self.status = "-"

        try:
            self.modified_client = datetime.strptime(entry["ModifiedClient"], "%Y-%m-%dT%H:%M:%S.%fZ")
        except:
            self.modified_client = datetime.strptime(entry["ModifiedClient"], "%Y-%m-%dT%H:%M:%SZ")
        

    def modified_str(self):
        return self.modified_client.strftime("%Y-%m-%d %H:%M:%S")


class Collection(Item):

    def __init__(self, entry, parent):
        super(Collection, self).__init__(entry, parent)
        pass

    def add_child(self, child: Item):
        self.children.append(child)
    


class Document(Item):

    def __init__(self, entry, parent: Collection):
        super(Document, self).__init__(entry, parent)
        
        self.path_raw = "data/%s" % self.uuid
        self.path_zip = "%s.zip" % self.path_raw
        self.path_svg = "%s/%s_" % (self.path_raw, self.name)
        self.path_rm_files = "%s/%s" % (self.path_raw, self.uuid)

        self.current_page = entry["CurrentPage"]
        self.current_svg_page = self.path_svg + str(self.current_page).zfill(5) + ".svg"
        self.status = "Available" if os.path.exists(self.path_raw) else "-"
        self.download_url = None
        self.blob_url = None


    def download_raw(self):
        
        if self.blob_url == None:
            self.blob_url = self.rm_client.get_blob_url(self.uuid)

        raw_file = self.rm_client.get_raw_file(self.blob_url)
        with open(self.path_zip, "wb") as out:
            out.write(raw_file)
        
        with zipfile.ZipFile(self.path_zip, "r") as zip_ref:
            zip_ref.extractall(self.path_raw)
        
        os.remove(self.path_zip)
        self.update_status = "Available"
    

    def download_svg(self):
        if self.status != "Available":
            self.download_raw()

        parser.rm_to_svg(self.path_rm_files, self.path_svg, background="white")
