from bs4 import BeautifulSoup
from bs4 import Tag
import requests
from collections import namedtuple
import os
import json
from collections import defaultdict

class DoomWorldWadScraper():
    """Collects WAD data present at www.doomworld.com
    This class is compatible to the website layout as of 10/10/2017"""

    def __init__(self):
        self.tuple_category = namedtuple("category",["name","url", "file_pages"])
        self.categories = dict()
        self.file_info = list()

    def _open_page(self, url):
        """Set up a BeautifulSoup for the given page"""
        self.session = requests.Session()
        page = self.session.get(url).text
        return BeautifulSoup(page, "lxml")

    def fetch_categories(self, url, exclude_list=[]):
        """Fetches every Download subcategory entry on doomworld.com starting from a game link like
        https://www.doomworld.com/files/category/64-doom/ and proceeds for just one level down the tree. 
        The ids in exclude_cat_id are skipped """
        soup = self._open_page(url)
        links = soup.find_all('a')
        for l in links:
            if l.has_attr('href') and "/category/" in l['href'] and l.find("strong") is not None:
                url = l['href']
                id = l['href'].split('/')[-2].split('-')[0]
                if not isinstance(l.contents[1], Tag) or int(id) in exclude_list:
                    # The considered element is not at the next nevel. e.g. ./deathmatch/a-z while on /levels/
                    # because we found the name of the class instead of a tag that contains it.
                    continue
                name = l.contents[1].contents[0]
                self.categories[id] = self.tuple_category(name=name, url=url, file_pages=[])
        return self.categories

    def _fetch_file_page_links(self, category_url, files_list=[]):
        """Fetches, for each category page, the list of the download pages that holds the data for each wad file by crawling
        through each list page, recursively.
        i.e. from an url of the type https://www.doomworld.com/files/category/<CATEGORYNAME>/?page=N
        navigates through all the N pages returning all the file urls like
        https://www.doomworld.com/files/file/<file-id>-<file-name>/"""
        found_files = files_list
        print ("Opening category page: " + category_url)
        soup = self._open_page(category_url)
        # Find the div containing the pagination design pattern and the file links
        mainDiv = soup.findAll("div", {"id": "ipsLayout_mainArea"})[0]
        file_page_links = [entry.find_all("a")[0] for entry in mainDiv.find_all("div", {"class":"ipsDataItem_main"})]
        found_files = found_files + [fpl['href'] for fpl in file_page_links]
        print("Current files: " + str(len(found_files)))

        # Check if there are more pages to crawl
        next_page_buttons = mainDiv.find_all("li", {"class" : "ipsPagination_next"})
        if len(next_page_buttons)>0 and "ipsPagination_inactive" not in next_page_buttons[0]['class']:
            new_category_url = next_page_buttons[0].a['href']
            print("The list continues to the page " + new_category_url)
            next_pages_files = self._fetch_file_page_links(new_category_url, files_list=found_files)
            found_files.append(next_pages_files)
        return found_files

    def _fetch_download_page_data(self, download_page_url, game_name=None, category_name=None):
        """Returns a dict containing all the useful data present in a download page"""

        # The data is stored in a defaultdict since not all the entries may be present on the page
        download_data = defaultdict(str)
        soup = self._open_page(download_page_url)
        # We focus only on the frame that contains the data
        main_div = soup.find_all("div", {"id" : "ipsLayout_mainArea"})[0].find_all("div",{'itemscope':'', 'itemtype':"http://schema.org/CreativeWork"})[0]
        rating_meta = main_div.div.find_all("meta")
        # These tags contain the main article with the headers for Title, Author, Description, Credits, Base, Build Time..
        level_info_tag_heads = [s.text.strip() for s in main_div.article.div.contents[1:-2:4]]  # These are the section heas (Author, About this file..)
        level_info_tag_content = [s.text.strip() for s in main_div.article.div.contents[3:-2:4]] # The corresponding content

        # Setting the title
        download_data['title'] = main_div.div.div.contents[1].div.text

        # This dict is to convert what is written to the webpage to the indices that are used in the json representation
        header_to_dict_index = defaultdict(lambda: "other", {
            'Author': 'author',
            'About This File': 'description',
            'Credits': 'credits',
            'Base': 'base',
            'Editors Used': 'editor_used',
            'Bugs': 'bugs',
            'Build Time': 'build_time'
        })

        for header, content in zip(level_info_tag_heads, level_info_tag_content):
            download_data[header_to_dict_index[header]] = content

        # Adding the metadata relative to the file itself (always present)
        file_information_panel = main_div.aside.div
        file_meta = file_information_panel.find_all("meta")

        download_data['rating_value'] = rating_meta[0]["content"]
        download_data['rating_count'] = rating_meta[1]["content"]
        download_data['page_visits'] = file_meta[0]["content"]
        download_data['downloads'] = file_meta[1]["content"]
        download_data['creation_date'] = file_meta[2]["content"]
        download_data['file_url'] = file_information_panel.a['href']
        download_data['game'] = game_name
        download_data['category'] = category_name

        return download_data

    def _download_and_save(self, url, local_path):
        """Downloads the file at 'url' to 'local_path' and returns the full path of the downloaded file or None on failure"""
        r = self.session.get(url)
        if r.status_code is not 200:
            print ("Failed to download the file: " + url)
            return None
        filename = r.url.split('/')[-1]
        with open(local_path+filename, "wb") as file:
            file.write(r.content)
        return local_path+filename

    def collect_wads(self, game_category_url, game_name, exclude_category_list=[], root_path = "./"):
        self.fetch_categories(game_category_url, exclude_list=exclude_category_list)
        # For each category found, collect the list of files and populate the relative tuple entry
        i = 0
        for cat_id in self.categories.keys():
            # Creates a new local folder if not present
            current_path = root_path + self.categories[cat_id].name + '/'
            #TODO: Create the directory for each category
            if not os.path.exists(current_path):
                os.makedirs(current_path)

            links = self._fetch_file_page_links(self.categories[cat_id].url)
            for link in links:
                print("Collecting " + link)
                newfile = self._fetch_download_page_data(link, game_name=game_name, category_name=self.categories[cat_id])
                # download the level file and store it on the local disk
                newfile['path'] = self._download_and_save(newfile['file_url'], current_path)
                newfile['name'] = newfile['path'].split("/")[-1]
                self.file_info.append(newfile)
        # Save the database
        with open(root_path+game_name+'database.json', 'w') as dbfile:
            json.dump(self.file_info, dbfile)

# Create a scraper for "Home>Downloads>idgames>levels>doom"
scraper = DoomWorldWadScraper()
# The link structure of each category page is: https://www.doomworld.com/files/category/##-???/
# where ## is a numerical id (eg. 64 for "doom") and ??? is the category name, such as "a-c"

# We are going to skip the "Deathmatch" (68), "Megawads" (85) and "Ports" (87) categories since they will be dealt with separately.
scraper.collect_wads(game_category_url='https://www.doomworld.com/files/category/64-doom/', game_name="Doom", exclude_category_list=[68, 85, 87], root_path="./database/doom/")
#scraper.collect_wads(game_category_url='https://www.doomworld.com/files/category/100-doom2/', game_name="Doom", exclude_category_list=[104, 129, 131], root_path="./database/doomII/")

