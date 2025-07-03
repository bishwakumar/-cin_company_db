from api.search import fetch_and_store_profiles
from db.models import create_search_table

def main():
    create_search_table()
    fetch_and_store_profiles()
    # next: save to DB in batches

if __name__ == "__main__":
    main()
