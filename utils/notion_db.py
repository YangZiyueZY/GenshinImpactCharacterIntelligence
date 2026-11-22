"""Mirror new characters into the author's Notion database (optional).

Fixes vs. the previous revision
  * the Notion client is created lazily, so importing this module (and running
    the whole pipeline) no longer requires the notion_client package or the
    NOTION_GENSHIN token; the step is simply skipped when they are absent
  * unknown properties in the remote schema no longer raise KeyError
"""

import os

DATABASE_ID = "482ae398eca5496aaa0b28c87bc8ba70"

_client = None


def get_client():
    global _client
    if _client is None:
        token = os.getenv("NOTION_GENSHIN")
        if not token:
            raise RuntimeError("NOTION_GENSHIN is not set")
        try:
            from notion_client import Client
        except ImportError as e:
            raise RuntimeError("notion_client is not installed") from e
        _client = Client(auth=token, timeout_ms=10000)
    return _client


def getProp(page, prop):
    prop_dict = page["properties"][prop]
    prop_type = prop_dict["type"]
    if prop_type in ("rich_text", "title"):
        content = prop_dict[prop_type]
        value = content[0]["plain_text"] if len(content) else ""
    elif prop_type == "select":
        value = (prop_dict[prop_type] or {}).get("name")
    else:
        value = prop_dict[prop_type]
    return value


def fillProps(data, schema):
    d = {}
    for k in data:
        if data[k] is None or data[k] == "":
            continue
        spec = schema.get(k)
        if not spec:
            continue
        dtype = spec["type"]
        if dtype in ("rich_text", "title"):
            d[k] = {dtype: [{"text": {"content": str(data[k])}}]}
        elif dtype == "select":
            for option in spec["select"]["options"]:
                if option["name"] == str(data[k]):
                    d[k] = {"select": {"id": option["id"]}}
                    break
        else:
            d[k] = {dtype: data[k]}
    return d


def fetch_my_table():
    notion = get_client()
    response = notion.databases.query(DATABASE_ID, sorts=[
        {"property": "id", "direction": "descending"}])
    chars = {}
    for page in response["results"]:
        char = {}
        for prop in ("id", "name_zh", "name_en", "url_name", "ver"):
            try:
                char[prop] = getProp(page, prop)
            except KeyError:
                char[prop] = ""
        chars[char["name_zh"]] = char
    return chars


def update_remote_table(char_dict, new_names):
    if not new_names:
        print("  No new characters to send to Notion")
        return 0
    notion = get_client()
    keys = ["id", "name_zh", "name_en", "img_url", "ver", "gender", "region",
            "rarity", "weapon", "element", "height"]
    weapon_map = {
        "WEAPON_SWORD_ONE_HAND": "单手剑",
        "WEAPON_CLAYMORE": "双手剑",
        "WEAPON_POLE": "长柄武器",
        "WEAPON_BOW": "弓",
        "WEAPON_CATALYST": "法器",
    }
    height_map = {"BODY_LOLI": 1, "BODY_BOY": 2, "BODY_GIRL": 2,
                  "BODY_MALE": 3, "BODY_LADY": 3}
    gender_map = {"BODY_LOLI": "♀️", "BODY_GIRL": "♀️", "BODY_LADY": "♀️"}
    region_map = {
        "MONDSTADT": "蒙德", "LIYUE": "璃月", "INAZUMA": "稻妻", "SUMERU": "须弥",
        "FONTAINE": "枫丹", "NATLAN": "纳塔", "FATUI": "至冬", "SNEZHNAYA": "至冬",
        "NODKRAI": "挪德卡莱",
    }
    update_list = []
    for name in new_names:
        char = char_dict.get(name)
        if not char:
            continue
        entry = {k: char.get(k, "") for k in keys}
        entry["weapon"] = weapon_map.get(char.get("weaponType"), " ")[0]
        entry["height"] = height_map.get(char.get("bodyType"), 1)
        entry["gender"] = gender_map.get(char.get("bodyType"), "♂️")
        entry["region"] = region_map.get(char.get("region"), char.get("region", ""))
        update_list.append(entry)

    schema = notion.databases.retrieve(DATABASE_ID)["properties"]
    prev_table = fetch_my_table()
    added = 0
    for entry in update_list:
        if entry["name_zh"] in prev_table:
            continue
        notion.pages.create(parent={"database_id": DATABASE_ID},
                            properties=fillProps(entry, schema))
        added += 1
    print("  Added " + str(added) + " / " + str(len(update_list)) + " characters to Notion")
    return added
