import discord
from discord.ext import commands
from discord import app_commands
import json
import random
from datetime import datetime
import os
from copy import deepcopy

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True
intents.presences = True


bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

DATA_FILE = "/tmp/library.json"
USER_PREFS_FILE = "/tmp/user_prefs.json"

BOOK_CATEGORIES = ["Du ký", "Sử ký", "Sách nghiên cứu", "Tiểu thuyết", "Cấm thư"]
ITEMS_PER_PAGE = 10
MAX_IMAGE_SIZE = 5 * 1024 * 1024  # 5MB


def load_json(filename, default):
    try:
        if os.path.exists(filename):
            with open(filename, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return default


def save_json(filename, data):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


# Per-guild library data: {str(guild_id): {books, facts, rumors, config, next_id}}
_raw = load_json(DATA_FILE, {})
# Migrate old flat format (has "books" as top-level key) → start fresh per-guild
if "books" in _raw:
    library_data: dict = {}
else:
    library_data: dict = _raw

user_prefs = load_json(USER_PREFS_FILE, {})
drafts = {}
draft_message_map = {}  # user_id -> channel_id


def get_guild_data(guild_id) -> dict:
    """Return (and initialise if needed) the data bucket for a guild."""
    gid = str(guild_id)
    if gid not in library_data:
        library_data[gid] = {
            "books": [], "facts": [], "rumors": [],
            "config": {"forbidden_role": None},
            "next_id": 1,
        }
        save_json(DATA_FILE, library_data)
    gd = library_data[gid]
    for key in ("books", "facts", "rumors"):
        gd.setdefault(key, [])
    gd.setdefault("config", {"forbidden_role": None})
    gd["config"].setdefault("forbidden_role", None)
    gd.setdefault("next_id", 1)
    gd.setdefault("lore", {})
    lore = gd["lore"]
    lore.setdefault("library", [])
    lore.setdefault("librarian", [])
    lore.setdefault("welcome",  {"messages": [], "active": None})
    lore.setdefault("farewell", {"messages": [], "active": None})
    lore["welcome"].setdefault("messages", [])
    lore["welcome"].setdefault("active", None)
    lore["farewell"].setdefault("messages", [])
    lore["farewell"].setdefault("active", None)
    return gd


def ensure_data():
    changed = False
    for gid, gd in library_data.items():
        for key in ["books", "facts", "rumors"]:
            gd.setdefault(key, [])
            for item in gd[key]:
                if "id" not in item:
                    item["id"] = gd.get("next_id", 1)
                    gd["next_id"] = item["id"] + 1
                    changed = True
                item.setdefault("title", "")
                item.setdefault("content", "")
                item.setdefault("author", "????")
                item.setdefault("author_id", "")
                item.setdefault("category", None)
                item.setdefault("date", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                item.setdefault("ratings", [])
                item.setdefault("viewers", [])
                item.setdefault("image_url", None)
                item.setdefault("image_name", None)
                item.setdefault("type", key)
    if changed:
        save_json(DATA_FILE, library_data)


ensure_data()


STRINGS = {
    "vi": {
        "welcome": "👻 *Thủ thư ma hiện lên từ bóng tối và khẽ nói...*\n\nTôi có thể giúp gì cho bạn?",
        "read_ask": "📖 *Thủ thư ma hỏi:*\n\nBạn muốn đọc gì?",
        "write_ask": "✍️ *Tôi muốn...*",
        "write_new_ask": "🖊️ *Tôi sẽ viết...*",
        "book_action": "📚 *Tôi muốn đọc sách. Vui lòng...*",
        "fact_action": "📌 *Tôi muốn đọc một fact. Vui lòng...*",
        "rumor_action": "👀 *Tôi muốn nghe một tin đồn. Vui lòng...*",
        "category_ask": "🗂️ *Thủ thư ma hỏi:*\n\n\"Thể loại sách bạn muốn đọc là...?\"",
        "forbidden_deny": "🚫 Bạn chưa đạt đủ điều kiện để tiếp cận nội dung này.",
        "return_book": "Trả sách",
        "understood": "Đã hiểu",
        "vote": "⭐ Vote",
        "return_msg": "😊 *Bạn đã trả 📙 **{name}** về thư viện.*\n\nBạn có cần hỗ trợ gì thêm không?",
        "understood_msg": "😌 *Bạn đã đọc xong **{name}**.*\n\nBạn có cần hỗ trợ gì thêm không?",
        "return_book_msg": "😊 *Bạn đã trả lại sách. Thủ thư ma lặng lẽ cất sách lên kệ...*\n\nBạn muốn làm gì tiếp theo?",
        "fact_done_msg": "😌 *Bạn đã nghe xong một fact. Hy vọng nó hữu ích cho bạn...*\n\nBạn muốn làm gì tiếp theo?",
        "rumor_done_msg": "🤫 *Bạn đã nghe xong một tin đồn. Hãy giữ bí mật nhé...*\n\nBạn muốn làm gì tiếp theo?",
        "exit_confirm": "Nội dung bạn viết vẫn chưa được lưu lại, bạn có chắc là muốn thoát?",
        "stay": "Ở lại viết tiếp",
        "leave": "Vâng",
        "choose_language": "Chọn ngôn ngữ / Select Language",
        "empty": "Kho hiện đang trống.",
        "no_works_edit": "📭 *Thủ thư ma lật qua những trang sách...*\n\nBạn chưa có tác phẩm nào được lưu trong thư viện.",
        "choose_item": "Chọn tác phẩm từ danh sách bên dưới để đọc.",
        "catalog_hint": "Bấm vào các nút mũi tên để xem những tác phẩm còn lại.",
        "updated": "✅ *Phiên bản mới của nội dung bạn gửi đã được cập nhật lại.*",
        "no_permission": "Chỉ người mở giao diện này mới có thể thao tác.",
        "saved": "✨ *Đã gửi tác phẩm vào thư viện.*",
        "draft_missing": "Hiện chưa có dữ liệu nháp để gửi.",
        "attach_prompt": "Hãy gửi đúng 1 ảnh trong tin nhắn tiếp theo của bạn. Ảnh có thể bỏ trống. Dung lượng khuyến nghị an toàn: <= 4MB, tối đa 5MB.",
        "attach_saved": "Đã lưu ảnh minh họa.",
        "too_large": "Ảnh vượt quá 5MB, vui lòng chọn ảnh nhẹ hơn.",
        "write_full": "Vui lòng điền đầy đủ thông tin tác phẩm:",
        "write_full_rumors": "Vui lòng điền đầy đủ thông tin tác phẩm:\n\n*📝 Lưu ý: Đối với tin đồn, thông tin người tung tin đồn sẽ không được hiển thị.*",
        "chat_ask": "😊 *Hãy kể cho tôi nghe về...*",
        "search_ask": "🔍 *Thủ thư ma hỏi:*\n\nBạn muốn tìm thông tin gì?",
        "ask_more": "Hỏi thêm vấn đề khác",
        "picked_role": "Đã thiết lập role được phép đọc Cấm thư.",
        "clear_done": "Đã dọn sạch toàn bộ thư viện.",
        "cancelled": "Đã thoát.",
        "author_empty_fill": 'Bạn bỏ trống tên tác giả, hệ thống sẽ tự điền thành "????".',
        "admin_only": "Chỉ admin server mới dùng được lệnh này.",
        "synced": "Đã đồng bộ slash commands.",
        "random_pick_book": "🤔 *Thủ thư ma trầm tư suy nghĩ...*\n\n📚 Và đưa cho bạn một cuốn sách.",
        "random_pick_fact": "📜 *Thủ thư ma lật qua những trang ghi chép cũ...*\n\n📌 Và đọc cho bạn nghe một fact.",
        "random_pick_rumor": "🤫 *Thủ thư ma nhìn quanh xem có ai không...*\n\n👁️ Rồi ghé tai bạn và thì thầm một tin đồn.",
        "write_category_ask": "🗂️ *Thể loại tôi đang viết là:*",
        "lib_info_text": (
            "📜 *Thủ thư ma đưa mắt nhìn khắp thư viện rồi bắt đầu kể...*\n\n"
            "Thư viện này tồn tại từ trước khi Ekoland được thành lập. "
            "Những nhà khai phá đầu tiên của Ekoland đã tìm ra nơi này và thức tỉnh lại nó. "
            "Chính vì thế, ngoài những sách do chính cư dân của Ekoland viết, "
            "bên trong thư viện vẫn còn rất nhiều mật thư huyền bí không rõ tên tác giả."
        ),
        "about_you_text": (
            "😌 *Thủ thư ma ngồi xuống và nói nhỏ...*\n\n"
            "Tôi không nhớ những gì đã xảy ra với mình trong quá khứ. "
            "Thật ra điều đó với tôi cũng không quan trọng. "
            "Bạn chỉ cần biết một điều: Cho dù thế giới xung quanh có biến đổi như thế nào, "
            "tôi tuyệt đối sẽ không bao giờ rời khỏi thư viện này."
        ),
        "chat_most_read": "🤔 *Thủ thư ma trầm tư suy nghĩ...*\n\n📙 Và đưa cho bạn tác phẩm được đọc nhiều nhất.",
        "chat_top_rated": "✨ *Thủ thư ma suy nghĩ giây lát...*\n\n⭐ Và đưa cho bạn tác phẩm được đánh giá cao nhất.",
        "chat_newest": "👁️ *Thủ thư ma lướt qua những trang mới nhất...*\n\n✨ Và đưa cho bạn nội dung vừa được gửi đến.",
        "farewell": "🌕 *\"Hẹn gặp lại bạn vào lần sau.\"*\n\nThủ thư ma gật đầu chào tạm biệt bạn rồi nhẹ nhàng tan biến vào trong bóng tối.",
        # UI labels
        "btn_home": "🏠 Trang đầu",
        "btn_read": "Đọc",
        "btn_write": "Viết",
        "btn_chat": "Trò chuyện",
        "btn_search": "Tra cứu",
        "btn_exit": "Thoát",
        "btn_lang": "Chuyển ngôn ngữ",
        "btn_books": "Sách",
        "btn_rumors": "Tin đồn",
        "btn_my_writes": "Tôi muốn đọc lại những gì mình đã viết",
        "btn_catalog": "Cho tôi xem danh mục hiện có",
        "btn_random": "Gợi ý ngẫu nhiên",
        "btn_about_lib": "Thư viện này",
        "btn_about_you": "Về bạn",
        "btn_most_read": "Tác phẩm được đọc nhiều nhất trong tháng này",
        "btn_top_rated": "Tác phẩm có rating cao nhất",
        "btn_newest": "Tác phẩm mới nhất vừa được gửi",
        "btn_read_list": "Danh mục nội dung đã đọc",
        "btn_voted_list": "Danh mục nội dung đã vote",
        "btn_all_works": "Toàn bộ tác phẩm",
        "btn_all_authors": "Toàn bộ tác giả",
        "btn_write_new": "Viết nội dung mới",
        "btn_edit_existing": "Sửa lại nội dung đã gửi",
        "btn_write_books": "Sách (tối đa 4000 ký tự)",
        "btn_write_facts": "Fact (tối đa 4000 ký tự)",
        "btn_write_rumors": "Tin đồn (tối đa 4000 ký tự)",
        "btn_clear_role": "Xoá role hiện tại",
        "btn_manage_del": "🗑️ Quản lý nội dung",
        "btn_manage_lore": "🧿 Quản lý Lore",
        "lore_menu_title": "🧿 Quản lý Lore thư viện",
        "lore_library_btn": "📜 Lore thư viện",
        "lore_librarian_btn": "👻 Lore thủ thư",
        "lore_welcome_btn": "👋 Lời chào mở đầu",
        "lore_farewell_btn": "🌕 Lời tạm biệt",
        "btn_add_lore": "➕ Thêm mới",
        "btn_edit_lore": "✏️ Sửa",
        "btn_del_lore": "🗑️ Xoá",
        "btn_set_active": "✅ Dùng câu này",
        "lore_empty": "*(Chưa có câu nào — đang dùng câu mặc định)*",
        "lore_add_modal_title": "Thêm nội dung lore mới",
        "lore_edit_modal_title": "Sửa nội dung lore",
        "lore_greet_modal_title": "Thêm lời chào mới",
        "lore_greet_edit_title": "Sửa lời chào",
        "lore_input_label": "Nội dung (tối đa 2000 ký tự)",
        "lore_saved": "✅ Đã lưu.",
        "lore_deleted": "🗑️ Đã xoá.",
        "lore_active_set": "✅ Đã chọn làm câu chào sử dụng.",
        "lore_min_warn": "⚠️ Phải giữ ít nhất 1 câu. Không thể xoá.",
        "lore_select_first": "Hãy chọn 1 mục từ danh sách trước.",
        "btn_back": "◀ Quay lại",
        "btn_cancel": "❌ Huỷ",
        "btn_confirm_del_all": "☢️ Xác nhận xoá toàn bộ",
        "btn_confirm_del_single": "✅ Xác nhận xoá",
        "btn_confirm_del_n": "✅ Xác nhận xoá {n} tác phẩm",
        "btn_del_single": "🗑️ Xoá 1 tác phẩm",
        "btn_del_author_menu": "🖊️ Xoá theo bút danh",
        "btn_del_user_menu": "👤 Xoá theo người dùng",
        "btn_del_all_menu": "☢️ Xoá toàn bộ",
        "ph_sort": "Sắp xếp theo...",
        "ph_choose_work": "Chọn tác phẩm để đọc...",
        "ph_edit_work": "Sửa lại nội dung đã viết",
        "ph_sort_authors": "Sắp xếp tác giả...",
        "ph_choose_author": "Chọn tác giả để xem thêm...",
        "ph_sort_works": "Sắp xếp tác phẩm...",
        "ph_del_author": "Chọn bút danh muốn xoá toàn bộ...",
        "ph_del_user": "Chọn người dùng để xoá toàn bộ tác phẩm...",
        "ph_forbidden_role": "Chọn role được phép đọc Cấm thư...",
        "sort_title_az": "Tên tác phẩm A-Z",
        "sort_title_za": "Tên tác phẩm Z-A",
        "sort_author_az": "Tên tác giả A-Z",
        "sort_author_za": "Tên tác giả Z-A",
        "sort_rating": "Rating cao -> thấp",
        "sort_newest": "Mới nhất -> cũ nhất",
        "sort_oldest": "Cũ nhất -> mới nhất",
        "invite_continue": "Mời bạn tiếp tục:",
        "type_books": "Sách", "type_facts": "Fact", "type_rumors": "Tin đồn",
        "edit_title_book": "Sửa tên sách",
        "edit_title_fact": "Sửa tên fact",
        "edit_title_rumor": "Sửa tên tin đồn",
        "edit_author": "Sửa tên tác giả",
        "edit_category": "Sửa thể loại",
        "edit_content": "Sửa nội dung",
        "edit_image": "Đăng lại ảnh (nếu cần)",
        "edit_submit": "Gửi lại",
        "new_title_book": "Điền tên sách",
        "new_title_fact": "Điền tên fact",
        "new_title_rumor": "Điền tên tin đồn",
        "new_submit_book": "Gửi sách",
        "new_submit_fact": "Gửi fact",
        "new_submit_rumor": "Gửi tin đồn",
        "new_author": "Điền tên tác giả",
        "new_category": "Chọn thể loại",
        "new_content": "Điền nội dung",
        "new_image": "Ảnh minh họa (có thể bỏ trống)",
    },
    "en": {
        "welcome": "👻 *The Ghost Librarian materializes from the shadows...*\n\nHow can I help you?",
        "read_ask": "📖 *The Ghost Librarian asks:*\n\nWhat would you like to read?",
        "write_ask": "✍️ *I want to...*",
        "write_new_ask": "🖊️ *I will write...*",
        "book_action": "📚 *I want to read books. Please...*",
        "fact_action": "📌 *I want to read facts. Please...*",
        "rumor_action": "👀 *I want to read rumors. Please...*",
        "category_ask": "🗂️ *The Ghost Librarian asks:*\n\n\"Which book category would you like to read?\"",
        "forbidden_deny": "🚫 You do not meet the requirements to access this content.",
        "return_book": "Return Book",
        "understood": "Understood",
        "vote": "⭐ Vote",
        "return_msg": "😊 *You returned 📙 **{name}** to the library.*\n\nDo you need anything else?",
        "understood_msg": "😌 *You finished reading **{name}**.*\n\nDo you need anything else?",
        "return_book_msg": "😊 *You returned the book. The Ghost Librarian quietly places it back on the shelf...*\n\nWhat would you like to do next?",
        "fact_done_msg": "😌 *You finished reading a fact. Hope it was helpful...*\n\nWhat would you like to do next?",
        "rumor_done_msg": "🤫 *You finished hearing a rumor. Keep it a secret...*\n\nWhat would you like to do next?",
        "exit_confirm": "Your writing hasn't been saved. Are you sure you want to exit?",
        "stay": "Stay",
        "leave": "Yes",
        "choose_language": "Chọn ngôn ngữ / Select Language",
        "empty": "The library is currently empty.",
        "no_works_edit": "📭 *The Ghost Librarian flips through the pages...*\n\nYou have no works saved in the library yet.",
        "choose_item": "Choose a work from the dropdown below to read.",
        "catalog_hint": "Press the arrow buttons to see the remaining works.",
        "updated": "✅ *The new version of your submission has been updated.*",
        "no_permission": "Only the user who opened this interface can use it.",
        "saved": "✨ *The work has been submitted to the library.*",
        "draft_missing": "No draft data is available.",
        "attach_prompt": "Send exactly 1 image in your next message. The image is optional. Safe recommended size: <= 4MB, maximum 5MB.",
        "attach_saved": "Illustration saved.",
        "too_large": "The image exceeds 5MB. Please choose a smaller one.",
        "write_full": "Please fill in all required fields:",
        "write_full_rumors": "Please fill in all required fields:\n\n*📝 Note: For rumors, the identity of the person spreading the rumor will not be displayed.*",
        "chat_ask": "😊 *Tell me about...*",
        "search_ask": "🔍 *The Ghost Librarian asks:*\n\nWhat information are you looking for?",
        "ask_more": "Ask another question",
        "picked_role": "The role allowed to read forbidden books has been set.",
        "clear_done": "The entire library has been cleared.",
        "cancelled": "Exited.",
        "author_empty_fill": 'You left the author name blank, so it was automatically filled as "????".',
        "admin_only": "Only server admins can use this command.",
        "synced": "Slash commands synced.",
        "random_pick_book": "🤔 *The Ghost Librarian ponders...*\n\n📚 And hands you a book.",
        "random_pick_fact": "📜 *The Ghost Librarian flips through old notes...*\n\n📌 And reads you a fact.",
        "random_pick_rumor": "🤫 *The Ghost Librarian glances around...*\n\n👁️ Then leans close and whispers a rumor.",
        "write_category_ask": "🗂️ *The category I am writing is:*",
        "lib_info_text": (
            "📜 *The Ghost Librarian looks around the library and begins...*\n\n"
            "This library existed before Ekoland was founded. "
            "The first explorers of Ekoland discovered this place and awakened it. "
            "That is why, beyond the books written by Ekoland's own people, "
            "the library still holds many mysterious manuscripts with no known author."
        ),
        "about_you_text": (
            "😌 *The Ghost Librarian settles down and speaks quietly...*\n\n"
            "I do not remember what happened to me in the past. "
            "Truthfully, it does not matter much to me. "
            "There is only one thing you need to know: No matter how the world around us changes, "
            "I will never, ever leave this library."
        ),
        "chat_most_read": "🤔 *The Ghost Librarian ponders...*\n\n📙 And hands you the most-read work.",
        "chat_top_rated": "✨ *The Ghost Librarian thinks for a moment...*\n\n⭐ And hands you the highest-rated work.",
        "chat_newest": "👁️ *The Ghost Librarian scans the newest pages...*\n\n✨ And presents the latest addition to the library.",
        "farewell": "🌕 *\"Until we meet again.\"*\n\nThe Ghost Librarian bows gently and fades back into the shadows.",
        # UI labels
        "btn_home": "🏠 Home",
        "btn_read": "Read",
        "btn_write": "Write",
        "btn_chat": "Chat",
        "btn_search": "Search",
        "btn_exit": "Exit",
        "btn_lang": "Language",
        "btn_books": "Books",
        "btn_rumors": "Rumors",
        "btn_my_writes": "My Submitted Works",
        "btn_catalog": "Browse Catalog",
        "btn_random": "Random Pick",
        "btn_about_lib": "This Library",
        "btn_about_you": "About You",
        "btn_most_read": "Most Read This Month",
        "btn_top_rated": "Highest Rated",
        "btn_newest": "Newest Submission",
        "btn_read_list": "My Reading List",
        "btn_voted_list": "My Voted Works",
        "btn_all_works": "All Works",
        "btn_all_authors": "All Authors",
        "btn_write_new": "Write New Content",
        "btn_edit_existing": "Edit Existing Submission",
        "btn_write_books": "Books (max 5000 chars)",
        "btn_write_facts": "Facts (max 300 chars)",
        "btn_write_rumors": "Rumors (max 300 chars)",
        "btn_clear_role": "Remove Current Role",
        "btn_manage_del": "🗑️ Manage Content",
        "btn_manage_lore": "🧿 Manage Lore",
        "lore_menu_title": "🧿 Library Lore Manager",
        "lore_library_btn": "📜 Library Lore",
        "lore_librarian_btn": "👻 Librarian Lore",
        "lore_welcome_btn": "👋 Welcome Messages",
        "lore_farewell_btn": "🌕 Farewell Messages",
        "btn_add_lore": "➕ Add New",
        "btn_edit_lore": "✏️ Edit",
        "btn_del_lore": "🗑️ Delete",
        "btn_set_active": "✅ Use This",
        "lore_empty": "*(No entries — using default)*",
        "lore_add_modal_title": "Add New Lore Entry",
        "lore_edit_modal_title": "Edit Lore Entry",
        "lore_greet_modal_title": "Add New Greeting",
        "lore_greet_edit_title": "Edit Greeting",
        "lore_input_label": "Content (max 2000 chars)",
        "lore_saved": "✅ Saved.",
        "lore_deleted": "🗑️ Deleted.",
        "lore_active_set": "✅ Set as active greeting.",
        "lore_min_warn": "⚠️ Must keep at least 1 entry. Cannot delete.",
        "lore_select_first": "Please select an entry from the list first.",
        "btn_back": "◀ Back",
        "btn_cancel": "❌ Cancel",
        "btn_confirm_del_all": "☢️ Confirm Delete All",
        "btn_confirm_del_single": "✅ Confirm Delete",
        "btn_confirm_del_n": "✅ Confirm Delete {n} works",
        "btn_del_single": "🗑️ Delete a Work",
        "btn_del_author_menu": "🖊️ Delete by Pen Name",
        "btn_del_user_menu": "👤 Delete by User",
        "btn_del_all_menu": "☢️ Delete All",
        "ph_sort": "Sort by...",
        "ph_choose_work": "Select a work to read...",
        "ph_edit_work": "Edit your submission...",
        "ph_sort_authors": "Sort authors...",
        "ph_choose_author": "Select an author...",
        "ph_sort_works": "Sort works...",
        "ph_del_author": "Select a pen name to delete...",
        "ph_del_user": "Select a user to delete all their works...",
        "ph_forbidden_role": "Select role for Forbidden Books...",
        "sort_title_az": "Title A-Z",
        "sort_title_za": "Title Z-A",
        "sort_author_az": "Author A-Z",
        "sort_author_za": "Author Z-A",
        "sort_rating": "Rating (high → low)",
        "sort_newest": "Newest first",
        "sort_oldest": "Oldest first",
        "invite_continue": "Please continue:",
        "type_books": "Books", "type_facts": "Facts", "type_rumors": "Rumors",
        "edit_title_book": "Edit Book Title",
        "edit_title_fact": "Edit Fact Title",
        "edit_title_rumor": "Edit Rumor Title",
        "edit_author": "Edit Author Name",
        "edit_category": "Edit Category",
        "edit_content": "Edit Content",
        "edit_image": "Re-upload Image (if needed)",
        "edit_submit": "Resubmit",
        "new_title_book": "Enter Book Title",
        "new_title_fact": "Enter Fact Title",
        "new_title_rumor": "Enter Rumor Title",
        "new_submit_book": "Submit Book",
        "new_submit_fact": "Submit Fact",
        "new_submit_rumor": "Submit Rumor",
        "new_author": "Enter Author Name",
        "new_category": "Choose Category",
        "new_content": "Enter Content",
        "new_image": "Illustration (optional)",
    },
}


def get_lang(user_id):
    return user_prefs.get(str(user_id), "vi")


def get_text(user_id, key):
    lang = get_lang(user_id)
    return STRINGS[lang].get(key, STRINGS["vi"].get(key, key))


def get_lore_text(gdata, category):
    """Random pick from guild lore list (library/librarian), fallback to STRINGS default."""
    entries = gdata.get("lore", {}).get(category, [])
    if entries:
        return random.choice(entries)
    if category == "library":
        return STRINGS["vi"]["lib_info_text"]
    return STRINGS["vi"]["about_you_text"]


def get_welcome_text(gdata, lang="vi"):
    """Return active welcome message or STRINGS default."""
    bucket = gdata.get("lore", {}).get("welcome", {})
    msgs   = bucket.get("messages", [])
    active = bucket.get("active")
    if msgs:
        if active is not None and 0 <= active < len(msgs):
            return msgs[active]
        return msgs[0]
    return STRINGS[lang]["welcome"]


def get_farewell_text(gdata, lang="vi"):
    """Return active farewell message or STRINGS default."""
    bucket = gdata.get("lore", {}).get("farewell", {})
    msgs   = bucket.get("messages", [])
    active = bucket.get("active")
    if msgs:
        if active is not None and 0 <= active < len(msgs):
            return msgs[active]
        return msgs[0]
    return STRINGS[lang]["farewell"]


def next_item_id(gdata: dict) -> int:
    nid = gdata["next_id"]
    gdata["next_id"] += 1
    return nid


def is_admin_member(member: discord.Member):
    return member.guild_permissions.administrator


def user_can_access_forbidden(member: discord.Member):
    role_id = get_guild_data(member.guild.id)["config"].get("forbidden_role")
    if role_id is None:
        return False
    return any(role.id == role_id for role in member.roles)


def librarian_embed(text, color=0x4b0082):
    embed = discord.Embed(description=text, color=color)
    embed.set_author(name="📜 Thư Viện Cổ 📜")
    return embed


def base_item_embed(item, item_type):
    type_icon = {"books": "📘", "facts": "📗", "rumors": "📕"}[item_type]
    author = item.get("author", "????")

    if item_type == "rumors":
        description = item["content"][:4000]
    else:
        description = f"*— {author}*\n\n{item['content'][:3900]}"

    embed = discord.Embed(
        title=f"{type_icon} {item['title']}",
        description=description,
        color=discord.Color.blurple(),
    )
    if item_type == "books" and item.get("category"):
        embed.add_field(name="Thể loại", value=item["category"], inline=True)
    embed.add_field(name="⭐ Vote", value=str(len(item.get("ratings", []))), inline=True)
    embed.add_field(
        name="👁️ Lượt đọc", value=str(len(item.get("viewers", []))), inline=True
    )
    if item.get("image_url"):
        embed.set_image(url=item["image_url"])
    embed.set_footer(
        text=f"Ngày gửi: {item.get('date', '')} • Nếu bạn thích nội dung vừa đọc thì hãy để lại 1 ⭐ ủng hộ tác giả nhé ❤️"
    )
    return embed


def get_all_items(gdata: dict):
    result = []
    for key in ["books", "facts", "rumors"]:
        for item in gdata[key]:
            copied = deepcopy(item)
            copied["type"] = key
            result.append(copied)
    return result


def sort_items(items, sort_mode):
    items = list(items)
    if sort_mode == "a-z_title":
        items.sort(key=lambda x: x.get("title", "").lower())
    elif sort_mode == "z-a_title":
        items.sort(key=lambda x: x.get("title", "").lower(), reverse=True)
    elif sort_mode == "a-z_author":
        items.sort(key=lambda x: x.get("author", "").lower())
    elif sort_mode == "z-a_author":
        items.sort(key=lambda x: x.get("author", "").lower(), reverse=True)
    elif sort_mode == "rating":
        items.sort(key=lambda x: len(x.get("ratings", [])), reverse=True)
    elif sort_mode == "oldest":
        items.sort(key=lambda x: x.get("date", ""))
    else:
        items.sort(key=lambda x: x.get("date", ""), reverse=True)
    return items


def get_item_by_id(item_id, gdata: dict, data_type=None):
    data_types = [data_type] if data_type else ["books", "facts", "rumors"]
    for dt in data_types:
        for item in gdata[dt]:
            if item["id"] == item_id:
                return item, dt
    return None, None


def register_view(item, user_id):
    viewers = item.setdefault("viewers", [])
    uid = str(user_id)

    if uid == item.get("author_id"):
        if uid not in viewers:
            viewers.append(uid)
    else:
        viewers.append(uid)

    save_json(DATA_FILE, library_data)


class UserOnlyView(discord.ui.View):
    def __init__(self, user, timeout=300):
        super().__init__(timeout=timeout)
        self.user = user

    @property
    def guild_id(self):
        if isinstance(self.user, discord.Member):
            return self.user.guild.id
        return 0

    @property
    def gdata(self) -> dict:
        return get_guild_data(self.guild_id)

    @property
    def farewell_text(self) -> str:
        return get_farewell_text(self.gdata, get_lang(self.user.id))

    @property
    def welcome_text(self) -> str:
        return get_welcome_text(self.gdata, get_lang(self.user.id))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user.id:
            await interaction.response.send_message(
                get_text(self.user.id, "no_permission"), ephemeral=True
            )
            return False
        return True


class ExitConfirmView(UserOnlyView):
    def __init__(self, user, parent_view):
        super().__init__(user, timeout=60)
        self.parent_view = parent_view

    @discord.ui.button(label="Ở lại viết tiếp", style=discord.ButtonStyle.success)
    async def stay_btn(self, interaction: discord.Interaction, button: discord.ui.Button):

        # ❗ FIX QUAN TRỌNG: luôn phải response
        await interaction.response.edit_message(
            content=None,
            embed=librarian_embed(get_text(self.user.id, "continue_writing")),
            view=self.parent_view
        )

    @discord.ui.button(label="Thoát", style=discord.ButtonStyle.danger)
    async def exit_btn(self, interaction: discord.Interaction, button: discord.ui.Button):

        drafts.pop(self.user.id, None)
        draft_message_map.pop(self.user.id, None)

        await interaction.response.edit_message(
            content=None,
            embed=librarian_embed(get_text(self.user.id, "exited")),
            view=MainMenuView(self.user)
        )


class HomeButton(discord.ui.Button):
    def __init__(self, user, row=None):
        super().__init__(
            label="🏠 Trang đầu",  # 👈 sửa ở đây
            style=discord.ButtonStyle.secondary,
            row=row
        )
        self.user = user

    async def callback(self, interaction: discord.Interaction):

        # ❗ chống người khác bấm
        if interaction.user.id != self.user.id:
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "Bạn không thể dùng nút này.", ephemeral=True
                )
            else:
                await interaction.followup.send(
                    "Bạn không thể dùng nút này.", ephemeral=True
                )
            return

        embed = librarian_embed(get_text(self.user.id, "home"))
        view = MainMenuView(self.user)

        # 🔥 FIX QUAN TRỌNG: handle cả 2 trạng thái interaction
        try:
            if interaction.response.is_done():
                await interaction.edit_original_response(
                    content=None,
                    embed=embed,
                    view=view
                )
            else:
                await interaction.response.edit_message(
                    content=None,
                    embed=embed,
                    view=view
                )
        except Exception:
            # 🔒 fallback cuối cùng (tránh fail cứng)
            try:
                await interaction.followup.send(
                    embed=embed,
                    view=view,
                    ephemeral=True
                )
            except Exception:
                pass


class MainMenuView(UserOnlyView):
    def __init__(self, user):
        super().__init__(user, timeout=600)
        self.read_btn.label   = get_text(user.id, "btn_read")
        self.write_btn.label  = get_text(user.id, "btn_write")
        self.chat_btn.label   = get_text(user.id, "btn_chat")
        self.search_btn.label = get_text(user.id, "btn_search")
        self.exit_btn.label   = get_text(user.id, "btn_exit")
        self.lang_btn.label   = get_text(user.id, "btn_lang")
        if isinstance(user, discord.Member) and is_admin_member(user):
            admin_btn = discord.ui.Button(
                label="⚙️ Admin", style=discord.ButtonStyle.secondary, row=1
            )
            async def admin_callback(interaction: discord.Interaction):
                _ap = AdminPanelView(self.user)
                await interaction.response.edit_message(
                    content=None, embeds=[_ap.panel_embed()], view=_ap
                )
            admin_btn.callback = admin_callback
            self.add_item(admin_btn)

    @discord.ui.button(label="Đọc", style=discord.ButtonStyle.primary, row=0)
    async def read_btn(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.edit_message(
            content=None,
            embed=librarian_embed(get_text(self.user.id, "read_ask")),
            view=ReadMenuView(self.user),
        )

    @discord.ui.button(label="Viết", style=discord.ButtonStyle.primary, row=0)
    async def write_btn(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.edit_message(
            content=None,
            embed=librarian_embed(get_text(self.user.id, "write_ask")),
            view=WriteMainView(self.user),
        )

    @discord.ui.button(label="Trò chuyện", style=discord.ButtonStyle.primary, row=0)
    async def chat_btn(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.edit_message(
            content=None,
            embed=librarian_embed(get_text(self.user.id, "chat_ask")),
            view=ChatMenuView(self.user),
        )

    @discord.ui.button(label="Tra cứu", style=discord.ButtonStyle.success, row=0)
    async def search_btn(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.edit_message(
            content=None,
            embed=librarian_embed(get_text(self.user.id, "search_ask")),
            view=SearchMenuView(self.user),
        )

    @discord.ui.button(label="Thoát", style=discord.ButtonStyle.danger, row=1)
    async def exit_btn(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.edit_message(content=None, embeds=[librarian_embed(self.farewell_text)], view=None)

    @discord.ui.button(
        label="Chuyển ngôn ngữ", style=discord.ButtonStyle.secondary, row=1
    )
    async def lang_btn(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.edit_message(
            content=get_text(self.user.id, "choose_language"),
            view=LanguageView(self.user),
            embed=None,
        )


class AdminPanelView(UserOnlyView):
    def __init__(self, user):
        super().__init__(user, timeout=300)

        role_select = discord.ui.RoleSelect(
            placeholder=get_text(user.id, "ph_forbidden_role"),
            min_values=1,
            max_values=1,
            row=0,
        )

        async def role_select_callback(interaction: discord.Interaction):
            if not isinstance(interaction.user, discord.Member) or not is_admin_member(interaction.user):
                await interaction.response.send_message(
                    get_text(self.user.id, "admin_only"), ephemeral=True
                )
                return
            selected_role = role_select.values[0]
            self.gdata["config"]["forbidden_role"] = selected_role.id
            save_json(DATA_FILE, library_data)
            _ap = AdminPanelView(self.user)
            await interaction.response.edit_message(embeds=[_ap.panel_embed()], view=_ap)

        role_select.callback = role_select_callback
        self.add_item(role_select)

        clear_btn = discord.ui.Button(
            label=get_text(user.id, "btn_clear_role"), style=discord.ButtonStyle.danger, row=1
        )

        async def clear_callback(interaction: discord.Interaction):
            if not isinstance(interaction.user, discord.Member) or not is_admin_member(interaction.user):
                await interaction.response.send_message(
                    get_text(self.user.id, "admin_only"), ephemeral=True
                )
                return
            self.gdata["config"]["forbidden_role"] = None
            save_json(DATA_FILE, library_data)
            _ap = AdminPanelView(self.user)
            await interaction.response.edit_message(embeds=[_ap.panel_embed()], view=_ap)

        clear_btn.callback = clear_callback
        self.add_item(clear_btn)

        delete_btn = discord.ui.Button(label=get_text(user.id, "btn_manage_del"), style=discord.ButtonStyle.danger, row=2)
        async def delete_callback(interaction: discord.Interaction):
            if not isinstance(interaction.user, discord.Member) or not is_admin_member(interaction.user):
                await interaction.response.send_message(get_text(self.user.id, "admin_only"), ephemeral=True)
                return
            _dm = DeleteMenuView(self.user)
            await interaction.response.edit_message(embeds=[_dm.menu_embed()], view=_dm)
        delete_btn.callback = delete_callback
        self.add_item(delete_btn)

        lore_btn = discord.ui.Button(label=get_text(user.id, "btn_manage_lore"), style=discord.ButtonStyle.primary, row=3)
        async def lore_callback(interaction: discord.Interaction):
            if not isinstance(interaction.user, discord.Member) or not is_admin_member(interaction.user):
                await interaction.response.send_message(get_text(self.user.id, "admin_only"), ephemeral=True)
                return
            _lm = LoreMenuView(self.user)
            await interaction.response.edit_message(embeds=[_lm.menu_embed()], view=_lm)
        lore_btn.callback = lore_callback
        self.add_item(lore_btn)

        self.add_item(HomeButton(self.user, row=3))

    def panel_embed(self):
        role_id = self.gdata["config"].get("forbidden_role")
        embed = discord.Embed(title="⚙️ Cài đặt Admin — Cấm thư", color=0x4b0082)
        embed.set_author(name="📜 Thư Viện Cổ 📜")
        if role_id:
            embed.add_field(
                name="🔐 Role hiện tại",
                value=f"<@&{role_id}>",
                inline=False,
            )
            embed.add_field(
                name="",
                value="Dùng dropdown bên dưới để đổi sang role khác,\nhoặc nhấn **Xoá role** để khoá Cấm thư với tất cả.",
                inline=False,
            )
        else:
            embed.add_field(
                name="🔐 Role hiện tại",
                value="*(Chưa thiết lập — Cấm thư đang bị khoá với tất cả)*",
                inline=False,
            )
            embed.add_field(
                name="",
                value="Dùng dropdown bên dưới để chọn role được phép đọc Cấm thư.",
                inline=False,
            )
        return embed


class LanguageView(UserOnlyView):
    def __init__(self, user):
        super().__init__(user, timeout=120)
        self.exit_btn.label = get_text(user.id, "btn_exit")
        self.add_item(HomeButton(self.user, row=1))

    @discord.ui.button(label="English", style=discord.ButtonStyle.success)
    async def en_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_prefs[str(self.user.id)] = "en"
        save_json(USER_PREFS_FILE, user_prefs)
        await interaction.response.edit_message(
            content=None,
            embed=librarian_embed(self.welcome_text),
            view=MainMenuView(self.user),
        )

    @discord.ui.button(label="Tiếng Việt", style=discord.ButtonStyle.primary)
    async def vi_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_prefs[str(self.user.id)] = "vi"
        save_json(USER_PREFS_FILE, user_prefs)
        await interaction.response.edit_message(
            content=None,
            embed=librarian_embed(self.welcome_text),
            view=MainMenuView(self.user),
        )

    @discord.ui.button(label="Thoát", style=discord.ButtonStyle.danger)
    async def exit_btn(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.edit_message(content=None, embeds=[librarian_embed(self.farewell_text)], view=None)


class ReadMenuView(UserOnlyView):
    def __init__(self, user):
        super().__init__(user, timeout=600)
        self.books.label    = get_text(user.id, "btn_books")
        self.rumors.label   = get_text(user.id, "btn_rumors")
        self.my_works.label = get_text(user.id, "btn_my_writes")
        self.exit_btn.label = get_text(user.id, "btn_exit")
        self.add_item(HomeButton(self.user, row=3))

    @discord.ui.button(label="Sách", style=discord.ButtonStyle.primary, row=0)
    async def books(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            content=None,
            embed=librarian_embed(get_text(self.user.id, "book_action")),
            view=ReadTypeOptionView(self.user, "books"),
        )

    @discord.ui.button(label="Fact", style=discord.ButtonStyle.primary, row=0)
    async def facts(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            content=None,
            embed=librarian_embed(get_text(self.user.id, "fact_action")),
            view=ReadTypeOptionView(self.user, "facts"),
        )

    @discord.ui.button(label="Tin đồn", style=discord.ButtonStyle.primary, row=0)
    async def rumors(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            content=None,
            embed=librarian_embed(get_text(self.user.id, "rumor_action")),
            view=ReadTypeOptionView(self.user, "rumors"),
        )

    @discord.ui.button(
        label="Tôi muốn đọc lại những gì mình đã viết",
        style=discord.ButtonStyle.success,
        row=1,
    )
    async def my_works(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.edit_message(
            content=None,
            embed=librarian_embed(get_text(self.user.id, "read_ask")),
            view=MyWorksTypeView(self.user),
        )

    @discord.ui.button(label="Thoát", style=discord.ButtonStyle.danger, row=2)
    async def exit_btn(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.edit_message(content=None, embeds=[librarian_embed(self.farewell_text)], view=None)


class ReadTypeOptionView(UserOnlyView):
    def __init__(self, user, data_type):
        super().__init__(user, timeout=600)
        self.data_type = data_type
        self.catalog.label     = get_text(user.id, "btn_catalog")
        self.random_pick.label = get_text(user.id, "btn_random")
        self.exit_btn.label    = get_text(user.id, "btn_exit")
        self.add_item(HomeButton(self.user, row=2))

    @discord.ui.button(
        label="Cho tôi xem danh mục hiện có", style=discord.ButtonStyle.primary, row=0
    )
    async def catalog(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if self.data_type == "books":
            await interaction.response.edit_message(
                content=None,
                embed=librarian_embed(get_text(self.user.id, "category_ask")),
                view=BookCategoryPickView(self.user),
            )
        else:
            _cv = CatalogView(self.user, self.data_type)
            await interaction.response.edit_message(
                content=None,
                embeds=[_cv.page_embed()],
                view=_cv,
            )

    @discord.ui.button(
        label="Gợi ý ngẫu nhiên", style=discord.ButtonStyle.primary, row=0
    )
    async def random_pick(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        items = list(self.gdata[self.data_type])

        if self.data_type == "books":
            filtered = []
            for item in items:
                if item.get("category") == "Cấm thư":
                    if isinstance(
                        interaction.user, discord.Member
                    ) and user_can_access_forbidden(interaction.user):
                        filtered.append(item)
                else:
                    filtered.append(item)
            items = filtered

        if not items:
            await interaction.response.send_message(
                get_text(self.user.id, "empty"), ephemeral=True
            )
            return

        item = random.choice(items)
        register_view(item, self.user.id)
        item_embed = base_item_embed(item, self.data_type)
        pick_key = {"books": "random_pick_book", "facts": "random_pick_fact", "rumors": "random_pick_rumor"}.get(self.data_type, "random_pick_book")
        await interaction.response.edit_message(
            content=None,
            embeds=[librarian_embed(get_text(self.user.id, pick_key)), item_embed],
            view=PostReadView(self.user, item["id"], self.data_type),
        )

    @discord.ui.button(label="Thoát", style=discord.ButtonStyle.danger, row=1)
    async def exit_btn(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.edit_message(content=None, embeds=[librarian_embed(self.farewell_text)], view=None)


class BookCategoryPickView(UserOnlyView):
    def __init__(self, user):
        super().__init__(user, timeout=600)

        for idx, cat in enumerate(BOOK_CATEGORIES):
            btn = discord.ui.Button(
                label=cat, style=discord.ButtonStyle.secondary, row=idx // 3
            )

            async def callback(interaction, category=cat):
                if category == "Cấm thư":
                    if not isinstance(
                        interaction.user, discord.Member
                    ) or not user_can_access_forbidden(interaction.user):
                        await interaction.response.send_message(
                            get_text(self.user.id, "forbidden_deny"), ephemeral=True
                        )
                        return

                _cv = CatalogView(self.user, "books", category=category)
                await interaction.response.edit_message(
                    content=None,
                    embeds=[_cv.page_embed()],
                    view=_cv,
                )

            btn.callback = callback
            self.add_item(btn)

        exit_btn = discord.ui.Button(
            label="Thoát", style=discord.ButtonStyle.danger, row=2
        )

        async def exit_callback(interaction: discord.Interaction):
            await interaction.response.edit_message(
                content=None, embeds=[librarian_embed(self.farewell_text)], view=None
            )

        exit_btn.callback = exit_callback
        self.add_item(exit_btn)
        self.add_item(HomeButton(self.user, row=3))


class PostReadView(UserOnlyView):
    def __init__(self, user, item_id, data_type):
        super().__init__(user, timeout=600)
        self.item_id = item_id
        self.data_type = data_type
        self.vote_btn.label = get_text(user.id, "vote")
        self.back_btn.label = (
            get_text(user.id, "return_book")
            if data_type == "books"
            else get_text(user.id, "understood")
        )
        self.add_item(HomeButton(self.user, row=2))

    @discord.ui.button(label="⭐ Vote", style=discord.ButtonStyle.success, row=0)
    async def vote_btn(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        item, _ = get_item_by_id(self.item_id, self.gdata, self.data_type)
        if not item:
            await interaction.response.send_message(
                "Không tìm thấy tác phẩm.", ephemeral=True
            )
            return

        uid = str(self.user.id)
        if uid not in item["ratings"]:
            item["ratings"].append(uid)
            save_json(DATA_FILE, library_data)
            await interaction.response.send_message(
                "Cảm ơn bạn đã vote!", ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "Bạn đã vote tác phẩm này rồi.", ephemeral=True
            )

    @discord.ui.button(label="Trả sách", style=discord.ButtonStyle.secondary, row=0)
    async def back_btn(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        item, _ = get_item_by_id(self.item_id, self.gdata, self.data_type)
        if not item:
            await interaction.response.edit_message(
                content=None,
                embed=librarian_embed(self.welcome_text),
                view=MainMenuView(self.user),
            )
            return

        if self.data_type == "books":
            msg = get_text(self.user.id, "return_book_msg")
        elif self.data_type == "facts":
            msg = get_text(self.user.id, "fact_done_msg")
        else:
            msg = get_text(self.user.id, "rumor_done_msg")

        await interaction.response.edit_message(
            content=None,
            embed=librarian_embed(msg),
            view=MainMenuView(self.user),
        )

    @discord.ui.button(label="Thoát", style=discord.ButtonStyle.danger, row=1)
    async def exit_btn(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.edit_message(content=None, embeds=[librarian_embed(self.farewell_text)], view=None)


class CatalogView(UserOnlyView):
    def __init__(
        self,
        user,
        data_type,
        category=None,
        sort_mode="newest",
        page=0,
        only_owner=False,
        owner_id=None,
        edit_mode=False,
        custom_items=None,
    ):
        super().__init__(user, timeout=600)
        self.data_type = data_type
        self.category = category
        self.sort_mode = sort_mode
        self.page = page
        self.only_owner = only_owner
        self.owner_id = str(owner_id) if owner_id else None
        self.edit_mode = edit_mode
        self.custom_items = custom_items

        items = self._get_items()
        self.filtered_items = items
        self.total_pages = max(1, (len(items) - 1) // ITEMS_PER_PAGE + 1)
        self.page = max(0, min(page, self.total_pages - 1))

        start = self.page * ITEMS_PER_PAGE
        end = start + ITEMS_PER_PAGE
        current_items = items[start:end]
        self.current_items = current_items

        uid = user.id
        sort_options = [
            discord.SelectOption(label=get_text(uid, "sort_title_az"), value="a-z_title",  default=(sort_mode == "a-z_title")),
            discord.SelectOption(label=get_text(uid, "sort_title_za"), value="z-a_title",  default=(sort_mode == "z-a_title")),
            discord.SelectOption(label=get_text(uid, "sort_author_az"),value="a-z_author", default=(sort_mode == "a-z_author")),
            discord.SelectOption(label=get_text(uid, "sort_author_za"),value="z-a_author", default=(sort_mode == "z-a_author")),
            discord.SelectOption(label=get_text(uid, "sort_rating"),   value="rating",     default=(sort_mode == "rating")),
            discord.SelectOption(label=get_text(uid, "sort_newest"),   value="newest",     default=(sort_mode == "newest")),
            discord.SelectOption(label=get_text(uid, "sort_oldest"),   value="oldest",     default=(sort_mode == "oldest")),
        ]
        sort_select = discord.ui.Select(
            placeholder=get_text(uid, "ph_sort"), options=sort_options, row=0
        )
        sort_select.callback = self.sort_callback
        self.add_item(sort_select)

        if current_items:
            read_select = discord.ui.Select(
                placeholder=get_text(uid, "ph_choose_work"),
                options=[
                    discord.SelectOption(
                        label=item["title"][:100],
                        description=(item.get("author") or "????")[:100],
                        value=str(item["id"]),
                    )
                    for item in current_items
                ],
                row=1,
            )
            read_select.callback = self.select_callback
            self.add_item(read_select)

            if self.edit_mode:
                edit_select = discord.ui.Select(
                    placeholder=get_text(uid, "ph_edit_work"),
                    options=[
                        discord.SelectOption(
                            label=item["title"][:100], value=str(item["id"])
                        )
                        for item in current_items
                    ],
                    row=2,
                )
                edit_select.callback = self.edit_select_callback
                self.add_item(edit_select)

        prev_btn = discord.ui.Button(
            label="◀",
            style=discord.ButtonStyle.secondary,
            disabled=(self.page == 0),
            row=3,
        )
        page_btn = discord.ui.Button(
            label=f"Trang {self.page + 1}/{self.total_pages}",
            style=discord.ButtonStyle.secondary,
            disabled=True,
            row=3,
        )
        next_btn = discord.ui.Button(
            label="▶",
            style=discord.ButtonStyle.secondary,
            disabled=(self.page >= self.total_pages - 1),
            row=3,
        )
        exit_btn = discord.ui.Button(
            label=get_text(uid, "btn_exit"), style=discord.ButtonStyle.danger, row=3
        )

        async def prev_callback(interaction: discord.Interaction):
            _cv = CatalogView(
                self.user,
                self.data_type,
                category=self.category,
                sort_mode=self.sort_mode,
                page=self.page - 1,
                only_owner=self.only_owner,
                owner_id=self.owner_id,
                edit_mode=self.edit_mode,
                custom_items=self.custom_items,
            )
            await interaction.response.edit_message(
                content=None, embeds=[_cv.page_embed()], view=_cv
            )

        async def next_callback(interaction: discord.Interaction):
            _cv = CatalogView(
                self.user,
                self.data_type,
                category=self.category,
                sort_mode=self.sort_mode,
                page=self.page + 1,
                only_owner=self.only_owner,
                owner_id=self.owner_id,
                edit_mode=self.edit_mode,
                custom_items=self.custom_items,
            )
            await interaction.response.edit_message(
                content=None, embeds=[_cv.page_embed()], view=_cv
            )

        async def exit_callback(interaction: discord.Interaction):
            await interaction.response.edit_message(
                content=None, embeds=[librarian_embed(self.farewell_text)], view=None
            )

        prev_btn.callback = prev_callback
        next_btn.callback = next_callback
        exit_btn.callback = exit_callback

        self.add_item(prev_btn)
        self.add_item(page_btn)
        self.add_item(next_btn)
        self.add_item(exit_btn)
        self.add_item(HomeButton(self.user, row=4))

    def page_embed(self):
        type_labels = {"books": "📘 Sách", "facts": "📗 Fact", "rumors": "📕 Tin đồn"}
        type_label = type_labels.get(self.data_type, self.data_type)
        category_text = f" — {self.category}" if self.category else ""
        embed = discord.Embed(
            title=f"{type_label}{category_text} • Trang {self.page + 1}/{self.total_pages}",
            color=0x4b0082,
        )
        embed.set_author(name="📜 Thư Viện Cổ 📜")
        if not self.current_items:
            embed.description = "*(Không có nội dung nào trong danh mục này.)*"
        else:
            for i, item in enumerate(self.current_items, 1):
                parts = []
                if self.data_type != "rumors":
                    parts.append(f"*Tác giả: {item.get('author') or '????'}*")
                if self.data_type == "books" and item.get("category"):
                    parts.append(f"Thể loại: {item['category']}")
                votes = len(item.get("ratings", []))
                viewers = len(item.get("viewers", []))
                parts.append(f"⭐ {votes} • 👁️ {viewers}")
                embed.add_field(
                    name=f"{i}. {item['title']}",
                    value="\n".join(parts),
                    inline=False,
                )
        return embed

    def _get_items(self):
        if self.custom_items is not None:
            items = list(self.custom_items)
        else:
            items = list(self.gdata[self.data_type])

        if self.data_type == "books" and self.category:
            items = [x for x in items if x.get("category") == self.category]

        if self.only_owner and self.owner_id:
            items = [x for x in items if x.get("author_id") == self.owner_id]

        return sort_items(items, self.sort_mode)

    async def sort_callback(self, interaction: discord.Interaction):
        mode = interaction.data["values"][0]
        _cv = CatalogView(
            self.user,
            self.data_type,
            category=self.category,
            sort_mode=mode,
            page=0,
            only_owner=self.only_owner,
            owner_id=self.owner_id,
            edit_mode=self.edit_mode,
            custom_items=self.custom_items,
        )
        await interaction.response.edit_message(
            content=None, embeds=[_cv.page_embed()], view=_cv
        )

    async def select_callback(self, interaction: discord.Interaction):
        item_id = int(interaction.data["values"][0])
        item, dt = get_item_by_id(item_id, self.gdata, self.data_type)
        if not item:
            await interaction.response.send_message(
                "Không tìm thấy tác phẩm.", ephemeral=True
            )
            return

        if dt == "books" and item.get("category") == "Cấm thư":
            if not isinstance(
                interaction.user, discord.Member
            ) or not user_can_access_forbidden(interaction.user):
                await interaction.response.send_message(
                    get_text(self.user.id, "forbidden_deny"), ephemeral=True
                )
                return

        register_view(item, self.user.id)
        await interaction.response.edit_message(
            content=None,
            embed=base_item_embed(item, dt),
            view=PostReadView(self.user, item_id, dt),
        )

    async def edit_select_callback(self, interaction: discord.Interaction):
        item_id = int(interaction.data["values"][0])
        item, dt = get_item_by_id(item_id, self.gdata, self.data_type)

        if not item or item.get("author_id") != str(self.user.id):
            await interaction.response.send_message(
                "Bạn chỉ có thể sửa nội dung do chính mình gửi.", ephemeral=True
            )
            return

        drafts[self.user.id] = {
            "mode": "edit",
            "data_type": dt,
            "item_id": item_id,
            "title": item.get("title", ""),
            "author": item.get("author", "????"),
            "category": item.get("category"),
            "content": item.get("content", ""),
            "image_url": item.get("image_url"),
            "image_name": item.get("image_name"),
        }

        await interaction.response.edit_message(
            content=get_text(self.user.id, "write_full"),
            view=WriteEditorView(self.user, dt, edit_mode=True),
            embed=None,
        )


class MyWorksTypeView(UserOnlyView):
    def __init__(self, user):
        super().__init__(user, timeout=600)
        self.books.label    = get_text(user.id, "btn_books")
        self.rumors.label   = get_text(user.id, "btn_rumors")
        self.exit_btn.label = get_text(user.id, "btn_exit")
        self.add_item(HomeButton(self.user, row=2))

    @discord.ui.button(label="Sách", style=discord.ButtonStyle.primary, row=0)
    async def books(self, interaction: discord.Interaction, button: discord.ui.Button):
        _cv = CatalogView(self.user, "books", owner_id=self.user.id, only_owner=True, edit_mode=True)
        await interaction.response.edit_message(content=None, embeds=[_cv.page_embed()], view=_cv)

    @discord.ui.button(label="Fact", style=discord.ButtonStyle.primary, row=0)
    async def facts(self, interaction: discord.Interaction, button: discord.ui.Button):
        _cv = CatalogView(self.user, "facts", owner_id=self.user.id, only_owner=True, edit_mode=True)
        await interaction.response.edit_message(content=None, embeds=[_cv.page_embed()], view=_cv)

    @discord.ui.button(label="Tin đồn", style=discord.ButtonStyle.primary, row=0)
    async def rumors(self, interaction: discord.Interaction, button: discord.ui.Button):
        _cv = CatalogView(self.user, "rumors", owner_id=self.user.id, only_owner=True, edit_mode=True)
        await interaction.response.edit_message(content=None, embeds=[_cv.page_embed()], view=_cv)

    @discord.ui.button(label="Thoát", style=discord.ButtonStyle.danger, row=1)
    async def exit_btn(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.edit_message(content=None, embeds=[librarian_embed(self.farewell_text)], view=None)


class NoWorksView(UserOnlyView):
    def __init__(self, user):
        super().__init__(user, timeout=300)
        self.exit_btn.label = get_text(user.id, "btn_exit")
        self.add_item(HomeButton(self.user, row=1))

    @discord.ui.button(label="Thoát", style=discord.ButtonStyle.danger, row=0)
    async def exit_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            content=None, embeds=[librarian_embed(self.farewell_text)], view=None
        )


class WriteMainView(UserOnlyView):
    def __init__(self, user):
        super().__init__(user, timeout=600)
        self.new_content.label  = get_text(user.id, "btn_write_new")
        self.edit_content.label = get_text(user.id, "btn_edit_existing")
        self.exit_btn.label     = get_text(user.id, "btn_exit")
        self.add_item(HomeButton(self.user, row=2))

    @discord.ui.button(
        label="Viết nội dung mới", style=discord.ButtonStyle.success, row=0
    )
    async def new_content(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.edit_message(
            content=None,
            embed=librarian_embed(get_text(self.user.id, "write_new_ask")),
            view=WriteTypeSelectView(self.user),
        )

    @discord.ui.button(
        label="Sửa lại nội dung đã gửi", style=discord.ButtonStyle.primary, row=0
    )
    async def edit_content(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        uid = str(self.user.id)
        has_works = any(
            str(item.get("author_id")) == uid
            for dt in ("books", "facts", "rumors")
            for item in self.gdata.get(dt, [])
        )
        if not has_works:
            view = NoWorksView(self.user)
            await interaction.response.edit_message(
                content=None,
                embed=librarian_embed(get_text(self.user.id, "no_works_edit")),
                view=view,
            )
            return
        await interaction.response.edit_message(
            content=None,
            embed=librarian_embed(get_text(self.user.id, "read_ask")),
            view=MyWorksTypeView(self.user),
        )

    @discord.ui.button(label="Thoát", style=discord.ButtonStyle.danger, row=1)
    async def exit_btn(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if self.user.id in drafts:
            await interaction.response.edit_message(
                content=get_text(self.user.id, "exit_confirm"),
                view=ExitConfirmView(self.user, self),
            )
        else:
            await interaction.response.edit_message(
                content=None, embeds=[librarian_embed(self.farewell_text)], view=None
            )


class WriteTypeSelectView(UserOnlyView):
    def __init__(self, user):
        super().__init__(user, timeout=600)
        self.books.label    = get_text(user.id, "btn_write_books")
        self.facts.label    = get_text(user.id, "btn_write_facts")
        self.rumors.label   = get_text(user.id, "btn_write_rumors")
        self.exit_btn.label = get_text(user.id, "btn_exit")
        self.add_item(HomeButton(self.user, row=2))

    @discord.ui.button(
        label="Sách (tối đa 4000 ký tự)", style=discord.ButtonStyle.primary, row=0
    )
    async def books(self, interaction: discord.Interaction, button: discord.ui.Button):
        drafts[self.user.id] = {
            "mode": "new",
            "data_type": "books",
            "title": "",
            "author": "",
            "category": None,
            "content": "",
            "image_url": None,
            "image_name": None,
        }
        draft_message_map[self.user.id] = interaction.channel_id
        await interaction.response.edit_message(
            content=get_text(self.user.id, "write_full"),
            view=WriteEditorView(self.user, "books"),
        )

    @discord.ui.button(
        label="Fact (tối đa 4000 ký tự)", style=discord.ButtonStyle.primary, row=0
    )
    async def facts(self, interaction: discord.Interaction, button: discord.ui.Button):
        drafts[self.user.id] = {
            "mode": "new",
            "data_type": "facts",
            "title": "",
            "author": "",
            "category": None,
            "content": "",
            "image_url": None,
            "image_name": None,
        }
        draft_message_map[self.user.id] = interaction.channel_id
        await interaction.response.edit_message(
            content=get_text(self.user.id, "write_full"),
            view=WriteEditorView(self.user, "facts"),
        )

    @discord.ui.button(
        label="Tin đồn (tối đa 4000 ký tự)", style=discord.ButtonStyle.primary, row=0
    )
    async def rumors(self, interaction: discord.Interaction, button: discord.ui.Button):
        drafts[self.user.id] = {
            "mode": "new",
            "data_type": "rumors",
            "title": "",
            "author": "????",
            "category": None,
            "content": "",
            "image_url": None,
            "image_name": None,
        }
        draft_message_map[self.user.id] = interaction.channel_id
        await interaction.response.edit_message(
            content=get_text(self.user.id, "write_full_rumors"),
            view=WriteEditorView(self.user, "rumors"),
        )

    @discord.ui.button(label="Thoát", style=discord.ButtonStyle.danger, row=1)
    async def exit_btn(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.edit_message(
            content=get_text(self.user.id, "exit_confirm"),
            view=ExitConfirmView(self.user, self),
        )


class BookWriteCategoryView(UserOnlyView):
    def __init__(self, user):
        super().__init__(user, timeout=600)

        for idx, cat in enumerate(BOOK_CATEGORIES):
            btn = discord.ui.Button(
                label=cat, style=discord.ButtonStyle.secondary, row=idx // 3
            )

            async def callback(interaction, category=cat):
                drafts[self.user.id]["category"] = category
                await interaction.response.edit_message(
                    content=get_text(self.user.id, "write_full"),
                    view=WriteEditorView(self.user, "books"),
                )

            btn.callback = callback
            self.add_item(btn)

        exit_btn = discord.ui.Button(
            label="Thoát", style=discord.ButtonStyle.danger, row=2
        )

        async def exit_callback(interaction: discord.Interaction):
            await interaction.response.edit_message(
                content=get_text(self.user.id, "exit_confirm"),
                view=ExitConfirmView(self.user, self),
            )

        exit_btn.callback = exit_callback
        self.add_item(exit_btn)
        self.add_item(HomeButton(self.user, row=3))


class SingleTextModal(discord.ui.Modal):
    def __init__(self, user, field_name, title, label, max_length, current_value=""):
        super().__init__(title=title)
        self.user = user
        self.field_name = field_name

        self.input = discord.ui.TextInput(
            label=label,
            default=current_value,
            required=False if field_name == "author" else True,
            max_length=4000 if field_name == "content" else max_length,  # 🔥 fix cứng 4000
            style=discord.TextStyle.long
            if field_name == "content"
            else discord.TextStyle.short,
        )
        self.add_item(self.input)

    async def on_submit(self, interaction: discord.Interaction):
        if self.user.id not in drafts:
            await interaction.response.send_message(
                get_text(self.user.id, "draft_missing"), ephemeral=True
            )
            return

        value = self.input.value.strip()

        # 🔥 chống vượt 4000 backend
        if self.field_name == "content" and len(value) > 4000:
            await interaction.response.send_message(
                "Nội dung vượt quá 4000 ký tự.", ephemeral=True
            )
            return

        _dt = drafts[self.user.id]["data_type"]
        _wf_key = "write_full_rumors" if _dt == "rumors" else "write_full"

        # ===== AUTHOR =====
        if self.field_name == "author":
            if not value:
                value = "????"
                drafts[self.user.id]["author"] = value

                # ❗ FIX: chỉ dùng 1 response, không edit message thủ công nữa
                await interaction.response.edit_message(
                    content=get_text(self.user.id, _wf_key),
                    view=WriteEditorView(
                        self.user,
                        _dt,
                        edit_mode=(drafts[self.user.id].get("mode") == "edit"),
                    ),
                )

                # gửi thông báo riêng
                await interaction.followup.send(
                    get_text(self.user.id, "author_empty_fill"),
                    ephemeral=True
                )
                return

            drafts[self.user.id]["author"] = value

        # ===== OTHER FIELDS =====
        else:
            if not value:
                await interaction.response.send_message(
                    "Trường này không được bỏ trống.", ephemeral=True
                )
                return

            drafts[self.user.id][self.field_name] = value

        # 🔥 FIX QUAN TRỌNG NHẤT: luôn refresh view bằng response
        await interaction.response.edit_message(
            content=get_text(self.user.id, _wf_key),
            view=WriteEditorView(
                self.user,
                _dt,
                edit_mode=(drafts[self.user.id].get("mode") == "edit"),
            ),
        )

class WriteEditorView(UserOnlyView):
    def __init__(self, user, data_type, edit_mode=False):
        super().__init__(user, timeout=900)
        self.data_type = data_type
        self.edit_mode = edit_mode

        uid = user.id
        if edit_mode:
            if data_type == "books":
                self.title_btn.label = get_text(uid, "edit_title_book")
            elif data_type == "facts":
                self.title_btn.label = get_text(uid, "edit_title_fact")
            else:
                self.title_btn.label = get_text(uid, "edit_title_rumor")
            self.author_btn.label   = get_text(uid, "edit_author")
            self.category_btn.label = get_text(uid, "edit_category")
            self.content_btn.label  = get_text(uid, "edit_content")
            self.image_btn.label    = get_text(uid, "edit_image")
            self.submit_btn.label   = get_text(uid, "edit_submit")
        else:
            if data_type == "books":
                self.title_btn.label  = get_text(uid, "new_title_book")
                self.submit_btn.label = get_text(uid, "new_submit_book")
            elif data_type == "facts":
                self.title_btn.label  = get_text(uid, "new_title_fact")
                self.submit_btn.label = get_text(uid, "new_submit_fact")
            else:
                self.title_btn.label  = get_text(uid, "new_title_rumor")
                self.submit_btn.label = get_text(uid, "new_submit_rumor")

            self.author_btn.label   = get_text(uid, "new_author")
            self.category_btn.label = get_text(uid, "new_category")
            self.content_btn.label  = get_text(uid, "new_content")
            self.image_btn.label    = get_text(uid, "new_image")

        if data_type != "books":
            self.category_btn.disabled = True

        if data_type == "rumors":
            self.author_btn.disabled = True

        self.add_item(HomeButton(self.user, row=3))

    @discord.ui.button(label="Điền tên", style=discord.ButtonStyle.primary, row=0)
    async def title_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        current = drafts.get(self.user.id, {}).get("title", "")
        await interaction.response.send_modal(
            SingleTextModal(self.user, "title", "Tên tác phẩm", "Nhập tên", 150, current)
        )

    @discord.ui.button(label="Điền tên tác giả", style=discord.ButtonStyle.primary, row=0)
    async def author_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        current = drafts.get(self.user.id, {}).get("author", "")
        await interaction.response.send_modal(
            SingleTextModal(
                self.user,
                "author",
                "Tên tác giả",
                "Nhập tên tác giả / OC",
                100,
                current,
            )
        )

    @discord.ui.button(label="Chọn thể loại", style=discord.ButtonStyle.primary, row=0)
    async def category_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            content=None,
            embed=librarian_embed(get_text(self.user.id, "write_category_ask")),
            view=BookWriteCategoryView(self.user),
        )

    @discord.ui.button(label="Điền nội dung", style=discord.ButtonStyle.primary, row=1)
    async def content_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        current = drafts.get(self.user.id, {}).get("content", "")
        await interaction.response.send_modal(
            SingleTextModal(
                self.user,
                "content",
                "Nội dung",
                "Nhập nội dung (tối đa 4000 ký tự)",
                4000,
                current,
            )
        )

    @discord.ui.button(label="Ảnh minh họa", style=discord.ButtonStyle.secondary, row=1)
    async def image_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            get_text(self.user.id, "attach_prompt"), ephemeral=True
        )

    @discord.ui.button(label="Gửi", style=discord.ButtonStyle.success, row=2)
    async def submit_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        draft = drafts.get(self.user.id)
        if not draft:
            await interaction.response.send_message(
                get_text(self.user.id, "draft_missing"), ephemeral=True
            )
            return

        title = draft.get("title", "").strip()
        content = draft.get("content", "").strip()
        author = draft.get("author", "").strip() or "????"
        category = draft.get("category")

        # ❗ FIX CHÍNH: chặn 4000 ký tự cho cả 3 loại
        if len(content) > 4000:
            await interaction.response.send_message(
                "Nội dung vượt quá 4000 ký tự.", ephemeral=True
            )
            return

        if not title or not content:
            await interaction.response.send_message(
                "Bạn cần điền đủ các trường bắt buộc trước khi gửi.", ephemeral=True
            )
            return

        if self.data_type == "books" and not category:
            await interaction.response.send_message(
                "Bạn cần chọn thể loại sách trước khi gửi.", ephemeral=True
            )
            return

        if self.data_type == "rumors":
            author = "????"

        if draft.get("mode") == "edit":
            item_id = draft["item_id"]
            item, _ = get_item_by_id(item_id, self.gdata, self.data_type)

            if not item or item.get("author_id") != str(self.user.id):
                await interaction.response.send_message(
                    "Bạn chỉ có thể sửa nội dung do chính mình gửi.", ephemeral=True
                )
                return

            item["title"] = title
            item["content"] = content
            item["author"] = author
            item["category"] = category if self.data_type == "books" else None
            item["image_url"] = draft.get("image_url")
            item["image_name"] = draft.get("image_name")
            item["date"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            save_json(DATA_FILE, library_data)
            drafts.pop(self.user.id, None)
            draft_message_map.pop(self.user.id, None)

            await interaction.response.edit_message(
                content=None,
                embed=librarian_embed(get_text(self.user.id, "updated")),
                view=MainMenuView(self.user),
            )
        else:
            gd = self.gdata
            new_item = {
                "id": next_item_id(gd),
                "title": title,
                "content": content,
                "author": author,
                "author_id": str(self.user.id),
                "category": category if self.data_type == "books" else None,
                "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "ratings": [],
                "viewers": [],
                "image_url": draft.get("image_url"),
                "image_name": draft.get("image_name"),
                "type": self.data_type,
            }

            gd[self.data_type].append(new_item)
            save_json(DATA_FILE, library_data)
            drafts.pop(self.user.id, None)
            draft_message_map.pop(self.user.id, None)

            await interaction.response.edit_message(
                content=None,
                embed=librarian_embed(get_text(self.user.id, "saved")),
                view=MainMenuView(self.user),
            )

    @discord.ui.button(label="Thoát", style=discord.ButtonStyle.danger, row=2)
    async def exit_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            content=get_text(self.user.id, "exit_confirm"),
            view=ExitConfirmView(self.user, self),
            embed=None,
        )

class ChatMenuView(UserOnlyView):
    def __init__(self, user):
        super().__init__(user, timeout=600)
        self.lib_info.label   = get_text(user.id, "btn_about_lib")
        self.about_you.label  = get_text(user.id, "btn_about_you")
        self.most_read.label  = get_text(user.id, "btn_most_read")
        self.top_rated.label  = get_text(user.id, "btn_top_rated")
        self.newest_item.label= get_text(user.id, "btn_newest")
        self.exit_btn.label   = get_text(user.id, "btn_exit")
        self.add_item(HomeButton(self.user, row=3))

    @discord.ui.button(label="Thư viện này", style=discord.ButtonStyle.primary, row=0)
    async def lib_info(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.edit_message(
            content=None,
            embed=librarian_embed(get_lore_text(self.gdata, "library")),
            view=ChatBackView(self.user),
        )

    @discord.ui.button(label="Về bạn", style=discord.ButtonStyle.secondary, row=0)
    async def about_you(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.edit_message(
            content=None,
            embed=librarian_embed(get_lore_text(self.gdata, "librarian")),
            view=ChatBackView(self.user),
        )

    @discord.ui.button(
        label="Tác phẩm được đọc nhiều nhất trong tháng này",
        style=discord.ButtonStyle.secondary,
        row=1,
    )
    async def most_read(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        items = get_all_items(self.gdata)
        if not items:
            await interaction.response.send_message(
                get_text(self.user.id, "empty"), ephemeral=True
            )
            return
        best = max(items, key=lambda x: len(x.get("viewers", [])))
        item, dt = get_item_by_id(best["id"], self.gdata, best["type"])
        register_view(item, self.user.id)
        await interaction.response.edit_message(
            content=None,
            embeds=[librarian_embed(get_text(self.user.id, "chat_most_read")), base_item_embed(item, dt)],
            view=PostReadView(self.user, item["id"], dt),
        )

    @discord.ui.button(
        label="Tác phẩm có rating cao nhất", style=discord.ButtonStyle.secondary, row=1
    )
    async def top_rated(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        items = get_all_items(self.gdata)
        if not items:
            await interaction.response.send_message(
                get_text(self.user.id, "empty"), ephemeral=True
            )
            return
        best = max(items, key=lambda x: len(x.get("ratings", [])))
        item, dt = get_item_by_id(best["id"], self.gdata, best["type"])
        register_view(item, self.user.id)
        await interaction.response.edit_message(
            content=None,
            embeds=[librarian_embed(get_text(self.user.id, "chat_top_rated")), base_item_embed(item, dt)],
            view=PostReadView(self.user, item["id"], dt),
        )

    @discord.ui.button(
        label="Tác phẩm mới nhất vừa được gửi",
        style=discord.ButtonStyle.secondary,
        row=2,
    )
    async def newest_item(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        items = get_all_items(self.gdata)
        if not items:
            await interaction.response.send_message(
                get_text(self.user.id, "empty"), ephemeral=True
            )
            return
        best = max(items, key=lambda x: x.get("date", ""))
        item, dt = get_item_by_id(best["id"], self.gdata, best["type"])
        register_view(item, self.user.id)
        await interaction.response.edit_message(
            content=None,
            embeds=[librarian_embed(get_text(self.user.id, "chat_newest")), base_item_embed(item, dt)],
            view=PostReadView(self.user, item["id"], dt),
        )

    @discord.ui.button(label="Thoát", style=discord.ButtonStyle.danger, row=2)
    async def exit_btn(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.edit_message(content=None, embeds=[librarian_embed(self.farewell_text)], view=None)


class ChatBackView(UserOnlyView):
    def __init__(self, user):
        super().__init__(user, timeout=600)
        self.ask_more.label = get_text(user.id, "ask_more")
        self.exit_btn.label = get_text(user.id, "btn_exit")
        self.add_item(HomeButton(self.user, row=1))

    @discord.ui.button(label="Hỏi thêm vấn đề khác", style=discord.ButtonStyle.primary)
    async def ask_more(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.edit_message(
            content=None,
            embed=librarian_embed(get_text(self.user.id, "chat_ask")),
            view=ChatMenuView(self.user),
        )

    @discord.ui.button(label="Thoát", style=discord.ButtonStyle.danger)
    async def exit_btn(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.edit_message(content=None, embeds=[librarian_embed(self.farewell_text)], view=None)


class SearchMenuView(UserOnlyView):
    def __init__(self, user):
        super().__init__(user, timeout=600)
        self.read_history.label  = get_text(user.id, "btn_read_list")
        self.vote_history.label  = get_text(user.id, "btn_voted_list")
        self.all_works.label     = get_text(user.id, "btn_all_works")
        self.all_authors.label   = get_text(user.id, "btn_all_authors")
        self.exit_btn.label      = get_text(user.id, "btn_exit")
        self.add_item(HomeButton(self.user, row=3))

    @discord.ui.button(
        label="Danh mục nội dung đã đọc", style=discord.ButtonStyle.primary, row=0
    )
    async def read_history(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.edit_message(
            content=None,
            embed=librarian_embed(get_text(self.user.id, "search_ask")),
            view=SearchTypeView(self.user, "read"),
        )

    @discord.ui.button(
        label="Danh mục nội dung đã vote", style=discord.ButtonStyle.secondary, row=0
    )
    async def vote_history(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.edit_message(
            content=None,
            embed=librarian_embed(get_text(self.user.id, "search_ask")),
            view=SearchTypeView(self.user, "vote"),
        )

    @discord.ui.button(
        label="Toàn bộ tác phẩm", style=discord.ButtonStyle.secondary, row=1
    )
    async def all_works(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.edit_message(
            content=None,
            embed=librarian_embed(get_text(self.user.id, "search_ask")),
            view=SearchTypeView(self.user, "all"),
        )

    @discord.ui.button(
        label="Toàn bộ tác giả", style=discord.ButtonStyle.secondary, row=1
    )
    async def all_authors(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        _av = AuthorCatalogView(self.user)
        await interaction.response.edit_message(
            content=None, embeds=[_av.page_embed()], view=_av
        )

    @discord.ui.button(label="Thoát", style=discord.ButtonStyle.danger, row=2)
    async def exit_btn(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.edit_message(content=None, embeds=[librarian_embed(self.farewell_text)], view=None)


class SearchTypeView(UserOnlyView):
    def __init__(self, user, mode):
        super().__init__(user, timeout=600)
        self.mode = mode
        self.add_item(HomeButton(self.user, row=2))

    @discord.ui.button(label="Sách", style=discord.ButtonStyle.primary, row=0)
    async def books(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.show(interaction, "books")

    @discord.ui.button(label="Fact", style=discord.ButtonStyle.primary, row=0)
    async def facts(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.show(interaction, "facts")

    @discord.ui.button(label="Tin đồn", style=discord.ButtonStyle.primary, row=0)
    async def rumors(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.show(interaction, "rumors")

    @discord.ui.button(label="Thoát", style=discord.ButtonStyle.danger, row=1)
    async def exit_btn(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.edit_message(content=None, embeds=[librarian_embed(self.farewell_text)], view=None)

    async def show(self, interaction, data_type):
        uid = str(self.user.id)
        items = list(self.gdata[data_type])

        if self.mode == "read":
            items = [x for x in items if uid in x.get("viewers", [])]
        elif self.mode == "vote":
            items = [x for x in items if uid in x.get("ratings", [])]

        if not items:
            await interaction.response.send_message(
                get_text(self.user.id, "empty"), ephemeral=True
            )
            return

        _cv = CatalogView(self.user, data_type, custom_items=items)
        await interaction.response.edit_message(
            content=None, embeds=[_cv.page_embed()], view=_cv
        )


class AuthorCatalogView(UserOnlyView):
    def __init__(self, user, sort_mode="a-z", page=0):
        super().__init__(user, timeout=600)
        self.sort_mode = sort_mode
        self.page = page

        author_map = {}
        for item in get_all_items(self.gdata):
            author_name = (item.get("author") or "????").strip()
            author_map.setdefault(author_name, []).append(item)

        authors = list(author_map.keys())
        if sort_mode == "z-a":
            authors.sort(reverse=True, key=lambda x: x.lower())
        else:
            authors.sort(key=lambda x: x.lower())

        self.authors = authors
        self.author_map = author_map
        self.total_pages = max(1, (len(authors) - 1) // ITEMS_PER_PAGE + 1)
        self.page = max(0, min(page, self.total_pages - 1))

        start = self.page * ITEMS_PER_PAGE
        end = start + ITEMS_PER_PAGE
        current = authors[start:end]
        self.current_authors = current

        uid = user.id
        sort_select = discord.ui.Select(
            placeholder=get_text(uid, "ph_sort_authors"),
            options=[
                discord.SelectOption(label=get_text(uid, "sort_author_az"), value="a-z", default=(sort_mode == "a-z")),
                discord.SelectOption(label=get_text(uid, "sort_author_za"), value="z-a", default=(sort_mode == "z-a")),
            ],
            row=0,
        )
        sort_select.callback = self.sort_callback
        self.add_item(sort_select)

        if current:
            author_select = discord.ui.Select(
                placeholder=get_text(uid, "ph_choose_author"),
                options=[discord.SelectOption(label=a[:100], value=a) for a in current],
                row=1,
            )
            author_select.callback = self.author_callback
            self.add_item(author_select)

        prev_btn = discord.ui.Button(
            label="◀",
            style=discord.ButtonStyle.secondary,
            disabled=(self.page == 0),
            row=2,
        )
        page_btn = discord.ui.Button(
            label=f"Trang {self.page + 1}/{self.total_pages}",
            style=discord.ButtonStyle.secondary,
            disabled=True,
            row=2,
        )
        next_btn = discord.ui.Button(
            label="▶",
            style=discord.ButtonStyle.secondary,
            disabled=(self.page >= self.total_pages - 1),
            row=2,
        )
        exit_btn = discord.ui.Button(
            label=get_text(user.id, "btn_exit"), style=discord.ButtonStyle.danger, row=2
        )

        async def prev_callback(interaction: discord.Interaction):
            _av = AuthorCatalogView(self.user, self.sort_mode, self.page - 1)
            await interaction.response.edit_message(content=None, embeds=[_av.page_embed()], view=_av)

        async def next_callback(interaction: discord.Interaction):
            _av = AuthorCatalogView(self.user, self.sort_mode, self.page + 1)
            await interaction.response.edit_message(content=None, embeds=[_av.page_embed()], view=_av)

        async def exit_callback(interaction: discord.Interaction):
            await interaction.response.edit_message(content=None, embeds=[librarian_embed(self.farewell_text)], view=None)

        prev_btn.callback = prev_callback
        next_btn.callback = next_callback
        exit_btn.callback = exit_callback

        self.add_item(prev_btn)
        self.add_item(page_btn)
        self.add_item(next_btn)
        self.add_item(exit_btn)
        self.add_item(HomeButton(self.user, row=3))

    def page_embed(self):
        embed = discord.Embed(
            title=f"🖊️ Danh mục tác giả • Trang {self.page + 1}/{self.total_pages}",
            color=0x4b0082,
        )
        embed.set_author(name="📜 Thư Viện Cổ 📜")
        if not self.current_authors:
            embed.description = "*(Chưa có tác giả nào trong thư viện.)*"
        else:
            for author_name in self.current_authors:
                works = self.author_map.get(author_name, [])
                count = len(works)
                newest = max(works, key=lambda x: x.get("date", ""), default=None)
                newest_title = newest["title"] if newest else "—"
                embed.add_field(
                    name=author_name,
                    value=f"📝 {count} tác phẩm\n🆕 Mới nhất: *{newest_title}*",
                    inline=False,
                )
        return embed

    async def sort_callback(self, interaction: discord.Interaction):
        mode = interaction.data["values"][0]
        _av = AuthorCatalogView(self.user, mode, 0)
        await interaction.response.edit_message(
            content=None, embeds=[_av.page_embed()], view=_av
        )

    async def author_callback(self, interaction: discord.Interaction):
        author_name = interaction.data["values"][0]
        _wv = AuthorWorksView(self.user, author_name)
        await interaction.response.edit_message(
            content=None, embeds=[_wv.page_embed()], view=_wv
        )


class AuthorWorksView(UserOnlyView):
    def __init__(self, user, author_name, sort_mode="a-z_title", page=0):
        super().__init__(user, timeout=600)
        self.author_name = author_name
        self.sort_mode = sort_mode
        self.page = page

        items = [
            x for x in get_all_items(self.gdata) if (x.get("author") or "????") == author_name
        ]
        items = sort_items(items, sort_mode)

        self.items = items
        self.total_pages = max(1, (len(items) - 1) // ITEMS_PER_PAGE + 1)
        self.page = max(0, min(page, self.total_pages - 1))

        start = self.page * ITEMS_PER_PAGE
        end = start + ITEMS_PER_PAGE
        current = items[start:end]
        self.current_works = current

        uid = user.id
        sort_select = discord.ui.Select(
            placeholder=get_text(uid, "ph_sort_works"),
            options=[
                discord.SelectOption(label=get_text(uid, "sort_title_az"), value="a-z_title", default=(sort_mode == "a-z_title")),
                discord.SelectOption(label=get_text(uid, "sort_title_za"), value="z-a_title", default=(sort_mode == "z-a_title")),
                discord.SelectOption(label=get_text(uid, "sort_newest"),   value="newest",    default=(sort_mode == "newest")),
                discord.SelectOption(label=get_text(uid, "sort_oldest"),   value="oldest",    default=(sort_mode == "oldest")),
            ],
            row=0,
        )
        sort_select.callback = self.sort_callback
        self.add_item(sort_select)

        if current:
            item_select = discord.ui.Select(
                placeholder=get_text(uid, "ph_choose_work"),
                options=[
                    discord.SelectOption(label=i["title"][:100], value=str(i["id"]))
                    for i in current
                ],
                row=1,
            )
            item_select.callback = self.item_callback
            self.add_item(item_select)

        prev_btn = discord.ui.Button(
            label="◀",
            style=discord.ButtonStyle.secondary,
            disabled=(self.page == 0),
            row=2,
        )
        page_btn = discord.ui.Button(
            label=f"Trang {self.page + 1}/{self.total_pages}",
            style=discord.ButtonStyle.secondary,
            disabled=True,
            row=2,
        )
        next_btn = discord.ui.Button(
            label="▶",
            style=discord.ButtonStyle.secondary,
            disabled=(self.page >= self.total_pages - 1),
            row=2,
        )
        exit_btn = discord.ui.Button(
            label=get_text(uid, "btn_exit"), style=discord.ButtonStyle.danger, row=2
        )

        async def prev_callback(interaction: discord.Interaction):
            _wv = AuthorWorksView(self.user, self.author_name, self.sort_mode, self.page - 1)
            await interaction.response.edit_message(content=None, embeds=[_wv.page_embed()], view=_wv)

        async def next_callback(interaction: discord.Interaction):
            _wv = AuthorWorksView(self.user, self.author_name, self.sort_mode, self.page + 1)
            await interaction.response.edit_message(content=None, embeds=[_wv.page_embed()], view=_wv)

        async def exit_callback(interaction: discord.Interaction):
            await interaction.response.edit_message(content=None, embeds=[librarian_embed(self.farewell_text)], view=None)

        prev_btn.callback = prev_callback
        next_btn.callback = next_callback
        exit_btn.callback = exit_callback

        self.add_item(prev_btn)
        self.add_item(page_btn)
        self.add_item(next_btn)
        self.add_item(exit_btn)
        self.add_item(HomeButton(self.user, row=3))

    def page_embed(self):
        type_icons = {"books": "📘", "facts": "📗", "rumors": "📕"}
        total = len(self.items)
        embed = discord.Embed(
            title=f"✍️ {self.author_name} — {total} tác phẩm • Trang {self.page + 1}/{self.total_pages}",
            color=0x4b0082,
        )
        embed.set_author(name="📜 Thư Viện Cổ 📜")
        if not self.current_works:
            embed.description = "*(Tác giả chưa có tác phẩm nào.)*"
        else:
            for i, item in enumerate(self.current_works, 1):
                icon = type_icons.get(item.get("type", "books"), "📄")
                votes = len(item.get("ratings", []))
                viewers = len(item.get("viewers", []))
                embed.add_field(
                    name=f"{i}. {icon} {item['title']}",
                    value=f"⭐ {votes} • 👁️ {viewers}",
                    inline=False,
                )
        return embed

    async def sort_callback(self, interaction: discord.Interaction):
        mode = interaction.data["values"][0]
        _wv = AuthorWorksView(self.user, self.author_name, mode, 0)
        await interaction.response.edit_message(
            content=None, embeds=[_wv.page_embed()], view=_wv
        )

    async def item_callback(self, interaction: discord.Interaction):
        item_id = int(interaction.data["values"][0])
        item, dt = get_item_by_id(item_id, self.gdata)

        if not item:
            await interaction.response.send_message(
                "Không tìm thấy tác phẩm.", ephemeral=True
            )
            return

        if dt == "books" and item.get("category") == "Cấm thư":
            if not isinstance(
                interaction.user, discord.Member
            ) or not user_can_access_forbidden(interaction.user):
                await interaction.response.send_message(
                    get_text(self.user.id, "forbidden_deny"), ephemeral=True
                )
                return

        register_view(item, self.user.id)
        await interaction.response.edit_message(
            content=None,
            embed=base_item_embed(item, dt),
            view=PostReadView(self.user, item_id, dt),
        )


# ─── Admin delete helpers ──────────────────────────────────────────────

def delete_item_by_id(item_id, gdata: dict):
    for dt in ["books", "facts", "rumors"]:
        for i, item in enumerate(gdata[dt]):
            if item["id"] == item_id:
                removed = gdata[dt].pop(i)
                save_json(DATA_FILE, library_data)
                return removed, dt
    return None, None


async def notify_deletion(bot_client, item):
    author_id = item.get("author_id")
    title = item.get("title", "không rõ")
    if not author_id:
        return
    try:
        user = await bot_client.fetch_user(int(author_id))
        await user.send(f'📨 Tác phẩm **"{title}"** của bạn đã bị xóa khỏi kho dữ liệu của thư viện.')
    except Exception:
        pass


async def notify_batch_deletion(bot_client, removed_items):
    user_items: dict = {}
    for item in removed_items:
        aid = item.get("author_id")
        if aid:
            user_items.setdefault(aid, []).append(item.get("title", "?"))
    for aid, titles in user_items.items():
        try:
            user = await bot_client.fetch_user(int(aid))
            lines = "\n".join(f'• **"{t}"**' for t in titles)
            await user.send(f'📨 Các tác phẩm sau của bạn đã bị xóa khỏi kho dữ liệu của thư viện:\n{lines}')
        except Exception:
            pass


# ─── Admin delete views ────────────────────────────────────────────────

class AdminReturnView(UserOnlyView):
    def __init__(self, user):
        super().__init__(user, timeout=120)
        back_btn = discord.ui.Button(label=get_text(user.id, "btn_back"), style=discord.ButtonStyle.secondary, row=0)
        async def back_cb(interaction: discord.Interaction):
            _dm = DeleteMenuView(self.user)
            await interaction.response.edit_message(embeds=[_dm.menu_embed()], view=_dm)
        back_btn.callback = back_cb
        self.add_item(back_btn)
        self.add_item(HomeButton(self.user, row=0))


class DeleteAllConfirmView(UserOnlyView):
    def __init__(self, user):
        super().__init__(user, timeout=120)
        confirm_btn = discord.ui.Button(label=get_text(user.id, "btn_confirm_del_all"), style=discord.ButtonStyle.danger, row=0)
        cancel_btn  = discord.ui.Button(label=get_text(user.id, "btn_cancel"), style=discord.ButtonStyle.secondary, row=0)

        async def confirm_cb(interaction: discord.Interaction):
            gd = self.gdata
            gd["books"] = []
            gd["facts"] = []
            gd["rumors"] = []
            save_json(DATA_FILE, library_data)
            embed = discord.Embed(title="☢️ Đã xoá toàn bộ", description="Kho dữ liệu thư viện đã được dọn sạch.", color=0x4b0082)
            embed.set_author(name="📜 Thư Viện Cổ 📜")
            await interaction.response.edit_message(embeds=[embed], view=AdminReturnView(self.user))

        async def cancel_cb(interaction: discord.Interaction):
            _dm = DeleteMenuView(self.user)
            await interaction.response.edit_message(embeds=[_dm.menu_embed()], view=_dm)

        confirm_btn.callback = confirm_cb
        cancel_btn.callback  = cancel_cb
        self.add_item(confirm_btn)
        self.add_item(cancel_btn)

    def confirm_embed(self):
        total = sum(len(self.gdata[dt]) for dt in ["books", "facts", "rumors"])
        embed = discord.Embed(title="⚠️ Xác nhận xoá toàn bộ kho dữ liệu", color=0xFF0000)
        embed.set_author(name="📜 Thư Viện Cổ 📜")
        embed.add_field(name="📊 Tổng số tác phẩm sẽ bị xoá", value=str(total), inline=False)
        embed.set_footer(text="Hành động này không thể hoàn tác. Bạn chắc chắn chứ?")
        return embed


class DeleteConfirmItemView(UserOnlyView):
    def __init__(self, user, item, dt):
        super().__init__(user, timeout=120)
        self.item = item
        self.dt   = dt
        confirm_btn = discord.ui.Button(label=get_text(user.id, "btn_confirm_del_single"), style=discord.ButtonStyle.danger, row=0)
        cancel_btn  = discord.ui.Button(label=get_text(user.id, "btn_cancel"), style=discord.ButtonStyle.secondary, row=0)

        async def confirm_cb(interaction: discord.Interaction):
            removed, _ = delete_item_by_id(self.item["id"], self.gdata)
            if removed:
                await notify_deletion(interaction.client, removed)
            embed = discord.Embed(
                title="✅ Đã xoá thành công",
                description=f'Tác phẩm **"{self.item["title"]}"** đã được xoá khỏi kho dữ liệu.',
                color=0x4b0082,
            )
            embed.set_author(name="📜 Thư Viện Cổ 📜")
            await interaction.response.edit_message(embeds=[embed], view=AdminReturnView(self.user))

        async def cancel_cb(interaction: discord.Interaction):
            _tv = DeleteSelectTypeView(self.user)
            await interaction.response.edit_message(embeds=[_tv.panel_embed()], view=_tv)

        confirm_btn.callback = confirm_cb
        cancel_btn.callback  = cancel_cb
        self.add_item(confirm_btn)
        self.add_item(cancel_btn)

    def confirm_embed(self):
        type_labels = {"books": "Sách", "facts": "Fact", "rumors": "Tin đồn"}
        embed = discord.Embed(title="⚠️ Xác nhận xoá tác phẩm", color=0xFF6B00)
        embed.set_author(name="📜 Thư Viện Cổ 📜")
        embed.add_field(name="📖 Tác phẩm", value=self.item["title"], inline=False)
        embed.add_field(name="✍️ Tác giả",  value=self.item.get("author", "?"), inline=True)
        embed.add_field(name="📁 Thể loại", value=type_labels.get(self.dt, self.dt), inline=True)
        embed.set_footer(text="Bạn sắp xoá tác phẩm này khỏi kho dữ liệu của thư viện. Bạn chắc chắn chứ?")
        return embed


class DeleteSelectItemView(UserOnlyView):
    def __init__(self, user, dt):
        super().__init__(user, timeout=180)
        self.dt = dt
        items = sorted(self.gdata[dt], key=lambda x: x.get("date", ""), reverse=True)[:25]
        type_labels = {"books": "Sách", "facts": "Fact", "rumors": "Tin đồn"}
        if items:
            options = [
                discord.SelectOption(
                    label=item["title"][:100],
                    value=str(item["id"]),
                    description=f"{item.get('author', '?')} • {item.get('date', '')[:10]}",
                )
                for item in items
            ]
            select = discord.ui.Select(
                placeholder=f"Chọn {type_labels[dt]} muốn xoá...", options=options, row=0
            )
            async def select_cb(interaction: discord.Interaction):
                item_id = int(select.values[0])
                item, found_dt = get_item_by_id(item_id, self.gdata)
                if not item:
                    await interaction.response.send_message("Không tìm thấy tác phẩm.", ephemeral=True)
                    return
                _cv = DeleteConfirmItemView(self.user, item, found_dt)
                await interaction.response.edit_message(embeds=[_cv.confirm_embed()], view=_cv)
            select.callback = select_cb
            self.add_item(select)
        back_btn = discord.ui.Button(label=get_text(user.id, "btn_back"), style=discord.ButtonStyle.secondary, row=1)
        async def back_cb(interaction: discord.Interaction):
            _tv = DeleteSelectTypeView(self.user)
            await interaction.response.edit_message(embeds=[_tv.panel_embed()], view=_tv)
        back_btn.callback = back_cb
        self.add_item(back_btn)
        self.add_item(HomeButton(self.user, row=1))

    def panel_embed(self):
        type_labels = {"books": "Sách", "facts": "Fact", "rumors": "Tin đồn"}
        total = len(self.gdata[self.dt])
        embed = discord.Embed(title=f"🗑️ Xoá {type_labels[self.dt]}", color=0x4b0082)
        embed.set_author(name="📜 Thư Viện Cổ 📜")
        if not total:
            embed.description = f"*(Không có {type_labels[self.dt]} nào trong thư viện.)*"
        elif total > 25:
            embed.description = f"Hiển thị 25 tác phẩm mới nhất trong tổng số **{total}**."
        else:
            embed.description = "Chọn tác phẩm muốn xoá từ dropdown bên dưới."
        return embed


class DeleteSelectTypeView(UserOnlyView):
    def __init__(self, user):
        super().__init__(user, timeout=180)
        for label, emoji, dt in [("Sách", "📘", "books"), ("Fact", "📗", "facts"), ("Tin đồn", "📕", "rumors")]:
            btn = discord.ui.Button(label=label, emoji=emoji, style=discord.ButtonStyle.secondary, row=0)
            def make_type_cb(data_type):
                async def cb(interaction: discord.Interaction):
                    _dv = DeleteSelectItemView(self.user, data_type)
                    await interaction.response.edit_message(embeds=[_dv.panel_embed()], view=_dv)
                return cb
            btn.callback = make_type_cb(dt)
            self.add_item(btn)
        back_btn = discord.ui.Button(label=get_text(user.id, "btn_back"), style=discord.ButtonStyle.secondary, row=1)
        async def back_cb(interaction: discord.Interaction):
            _dm = DeleteMenuView(self.user)
            await interaction.response.edit_message(embeds=[_dm.menu_embed()], view=_dm)
        back_btn.callback = back_cb
        self.add_item(back_btn)
        self.add_item(HomeButton(self.user, row=1))

    def panel_embed(self):
        embed = discord.Embed(title="🗑️ Xoá tác phẩm — Chọn thể loại", color=0x4b0082)
        embed.set_author(name="📜 Thư Viện Cổ 📜")
        embed.description = "Chọn thể loại tác phẩm muốn xoá:"
        return embed


class DeleteByAuthorConfirmView(UserOnlyView):
    def __init__(self, user, author_name, count):
        super().__init__(user, timeout=120)
        self.author_name = author_name
        self.count = count
        confirm_btn = discord.ui.Button(label=get_text(user.id, "btn_confirm_del_n").format(n=count), style=discord.ButtonStyle.danger, row=0)
        cancel_btn  = discord.ui.Button(label=get_text(user.id, "btn_cancel"), style=discord.ButtonStyle.secondary, row=0)

        async def confirm_cb(interaction: discord.Interaction):
            gd = self.gdata
            removed_items = []
            for dt in ["books", "facts", "rumors"]:
                keep, rem = [], []
                for item in gd[dt]:
                    (rem if item.get("author") == self.author_name else keep).append(item)
                gd[dt] = keep
                removed_items.extend(rem)
            save_json(DATA_FILE, library_data)
            await notify_batch_deletion(interaction.client, removed_items)
            embed = discord.Embed(
                title="✅ Đã xoá thành công",
                description=f'Đã xoá **{len(removed_items)} tác phẩm** của bút danh **"{self.author_name}"**.',
                color=0x4b0082,
            )
            embed.set_author(name="📜 Thư Viện Cổ 📜")
            await interaction.response.edit_message(embeds=[embed], view=AdminReturnView(self.user))

        async def cancel_cb(interaction: discord.Interaction):
            _av = DeleteByAuthorView(self.user)
            await interaction.response.edit_message(embeds=[_av.panel_embed()], view=_av)

        confirm_btn.callback = confirm_cb
        cancel_btn.callback  = cancel_cb
        self.add_item(confirm_btn)
        self.add_item(cancel_btn)

    def confirm_embed(self):
        embed = discord.Embed(title="⚠️ Xác nhận xoá theo bút danh", color=0xFF6B00)
        embed.set_author(name="📜 Thư Viện Cổ 📜")
        embed.add_field(name="✍️ Bút danh", value=self.author_name, inline=False)
        embed.add_field(name="📊 Số tác phẩm sẽ bị xoá", value=str(self.count), inline=False)
        embed.set_footer(text="Bạn sắp xoá toàn bộ tác phẩm của bút danh này. Bạn chắc chắn chứ?")
        return embed


class DeleteByAuthorView(UserOnlyView):
    def __init__(self, user):
        super().__init__(user, timeout=180)
        author_map: dict = {}
        for dt in ["books", "facts", "rumors"]:
            for item in self.gdata[dt]:
                a = item.get("author", "Ẩn danh")
                author_map[a] = author_map.get(a, 0) + 1
        if author_map:
            options = [
                discord.SelectOption(label=a[:100], value=a[:100], description=f"{c} tác phẩm")
                for a, c in sorted(author_map.items(), key=lambda x: -x[1])[:25]
            ]
            select = discord.ui.Select(
                placeholder=get_text(user.id, "ph_del_author"), options=options, row=0
            )
            async def select_cb(interaction: discord.Interaction):
                author_name = select.values[0]
                gd = self.gdata
                count = sum(
                    1 for dt in ["books", "facts", "rumors"]
                    for item in gd[dt] if item.get("author") == author_name
                )
                _cv = DeleteByAuthorConfirmView(self.user, author_name, count)
                await interaction.response.edit_message(embeds=[_cv.confirm_embed()], view=_cv)
            select.callback = select_cb
            self.add_item(select)
        back_btn = discord.ui.Button(label=get_text(user.id, "btn_back"), style=discord.ButtonStyle.secondary, row=1)
        async def back_cb(interaction: discord.Interaction):
            _dm = DeleteMenuView(self.user)
            await interaction.response.edit_message(embeds=[_dm.menu_embed()], view=_dm)
        back_btn.callback = back_cb
        self.add_item(back_btn)
        self.add_item(HomeButton(self.user, row=1))

    def panel_embed(self):
        embed = discord.Embed(title="🖊️ Xoá theo bút danh", color=0x4b0082)
        embed.set_author(name="📜 Thư Viện Cổ 📜")
        embed.description = "Chọn bút danh từ dropdown. **Toàn bộ tác phẩm** dưới bút danh đó sẽ bị xoá."
        return embed


class DeleteByUserConfirmView(UserOnlyView):
    def __init__(self, user, target_user):
        super().__init__(user, timeout=120)
        self.target_user = target_user
        target_id = str(target_user.id)
        gd = self.gdata
        count = sum(
            1 for dt in ["books", "facts", "rumors"]
            for item in gd[dt] if item.get("author_id") == target_id
        )
        self.count = count
        confirm_btn = discord.ui.Button(label=get_text(user.id, "btn_confirm_del_n").format(n=count), style=discord.ButtonStyle.danger, row=0)
        cancel_btn  = discord.ui.Button(label=get_text(user.id, "btn_cancel"), style=discord.ButtonStyle.secondary, row=0)

        async def confirm_cb(interaction: discord.Interaction):
            gd = self.gdata
            removed_items = []
            for dt in ["books", "facts", "rumors"]:
                keep, rem = [], []
                for item in gd[dt]:
                    (rem if item.get("author_id") == target_id else keep).append(item)
                gd[dt] = keep
                removed_items.extend(rem)
            save_json(DATA_FILE, library_data)
            await notify_batch_deletion(interaction.client, removed_items)
            embed = discord.Embed(
                title="✅ Đã xoá thành công",
                description=f'Đã xoá **{len(removed_items)} tác phẩm** của <@{target_id}> khỏi kho dữ liệu.',
                color=0x4b0082,
            )
            embed.set_author(name="📜 Thư Viện Cổ 📜")
            await interaction.response.edit_message(embeds=[embed], view=AdminReturnView(self.user))

        async def cancel_cb(interaction: discord.Interaction):
            _uv = DeleteByUserView(self.user)
            await interaction.response.edit_message(embeds=[_uv.panel_embed()], view=_uv)

        confirm_btn.callback = confirm_cb
        cancel_btn.callback  = cancel_cb
        self.add_item(confirm_btn)
        self.add_item(cancel_btn)

    def confirm_embed(self):
        embed = discord.Embed(title="⚠️ Xác nhận xoá theo người dùng", color=0xFF6B00)
        embed.set_author(name="📜 Thư Viện Cổ 📜")
        embed.add_field(name="👤 Người dùng", value=f"<@{self.target_user.id}>", inline=False)
        embed.add_field(name="📊 Số tác phẩm sẽ bị xoá", value=str(self.count), inline=False)
        embed.set_footer(text="Bạn sắp xoá toàn bộ tác phẩm của người dùng này. Bạn chắc chắn chứ?")
        return embed


class DeleteByUserView(UserOnlyView):
    def __init__(self, user):
        super().__init__(user, timeout=180)
        user_select = discord.ui.UserSelect(
            placeholder=get_text(user.id, "ph_del_user"),
            min_values=1, max_values=1, row=0,
        )
        async def user_select_cb(interaction: discord.Interaction):
            target = user_select.values[0]
            _cv = DeleteByUserConfirmView(self.user, target)
            await interaction.response.edit_message(embeds=[_cv.confirm_embed()], view=_cv)
        user_select.callback = user_select_cb
        self.add_item(user_select)
        back_btn = discord.ui.Button(label=get_text(user.id, "btn_back"), style=discord.ButtonStyle.secondary, row=1)
        async def back_cb(interaction: discord.Interaction):
            _dm = DeleteMenuView(self.user)
            await interaction.response.edit_message(embeds=[_dm.menu_embed()], view=_dm)
        back_btn.callback = back_cb
        self.add_item(back_btn)
        self.add_item(HomeButton(self.user, row=1))

    def panel_embed(self):
        embed = discord.Embed(title="👤 Xoá theo người dùng", color=0x4b0082)
        embed.set_author(name="📜 Thư Viện Cổ 📜")
        embed.description = "Chọn người dùng Discord từ dropdown. **Toàn bộ tác phẩm** do người đó đăng sẽ bị xoá."
        return embed


class DeleteMenuView(UserOnlyView):
    def __init__(self, user):
        super().__init__(user, timeout=300)
        uid = user.id
        for label, style, row, action in [
            (get_text(uid, "btn_del_single"),      discord.ButtonStyle.secondary, 0, "single"),
            (get_text(uid, "btn_del_author_menu"), discord.ButtonStyle.secondary, 0, "author"),
            (get_text(uid, "btn_del_user_menu"),   discord.ButtonStyle.secondary, 0, "user"),
            (get_text(uid, "btn_del_all_menu"),    discord.ButtonStyle.danger,    1, "all"),
        ]:
            btn = discord.ui.Button(label=label, style=style, row=row)
            def make_cb(act):
                async def cb(interaction: discord.Interaction):
                    if act == "single":
                        _v = DeleteSelectTypeView(self.user)
                        await interaction.response.edit_message(embeds=[_v.panel_embed()], view=_v)
                    elif act == "author":
                        _v = DeleteByAuthorView(self.user)
                        await interaction.response.edit_message(embeds=[_v.panel_embed()], view=_v)
                    elif act == "user":
                        _v = DeleteByUserView(self.user)
                        await interaction.response.edit_message(embeds=[_v.panel_embed()], view=_v)
                    elif act == "all":
                        _v = DeleteAllConfirmView(self.user)
                        await interaction.response.edit_message(embeds=[_v.confirm_embed()], view=_v)
                return cb
            btn.callback = make_cb(action)
            self.add_item(btn)
        self.add_item(HomeButton(self.user, row=1))

    def menu_embed(self):
        books  = len(self.gdata["books"])
        facts  = len(self.gdata["facts"])
        rumors = len(self.gdata["rumors"])
        embed = discord.Embed(title="🗑️ Quản lý xoá nội dung", color=0x4b0082)
        embed.set_author(name="📜 Thư Viện Cổ 📜")
        embed.add_field(
            name="📊 Kho dữ liệu hiện tại",
            value=f"📘 Sách: {books}\n📗 Fact: {facts}\n📕 Tin đồn: {rumors}",
            inline=False,
        )
        embed.add_field(
            name="⚠️ Lưu ý",
            value="Sau khi xoá, tác giả sẽ được thông báo qua tin nhắn riêng (DM).",
            inline=False,
        )
        return embed


# ─── Lore management ──────────────────────────────────────────────────

class LoreTextModal(discord.ui.Modal):
    def __init__(self, user, gdata, category, edit_index=None, is_greeting=False):
        uid = user.id
        if edit_index is not None:
            title = get_text(uid, "lore_greet_edit_title" if is_greeting else "lore_edit_modal_title")
        else:
            title = get_text(uid, "lore_greet_modal_title" if is_greeting else "lore_add_modal_title")
        super().__init__(title=title[:45])
        self.user        = user
        self.gdata       = gdata
        self.category    = category
        self.edit_index  = edit_index
        self.is_greeting = is_greeting

        existing = ""
        if edit_index is not None:
            if is_greeting:
                existing = gdata["lore"][category]["messages"][edit_index]
            else:
                existing = gdata["lore"][category][edit_index]

        self.lore_input = discord.ui.TextInput(
            label=get_text(uid, "lore_input_label")[:45],
            style=discord.TextStyle.paragraph,
            default=existing,
            max_length=2000,
            required=True,
        )
        self.add_item(self.lore_input)

    async def on_submit(self, interaction: discord.Interaction):
        text = self.lore_input.value.strip()
        uid  = self.user.id
        gd   = self.gdata
        cat  = self.category
        if self.is_greeting:
            msgs = gd["lore"][cat]["messages"]
            if self.edit_index is not None:
                msgs[self.edit_index] = text
            else:
                msgs.append(text)
            save_json(DATA_FILE, library_data)
            _v = GreetingListView(self.user, cat)
            await interaction.response.edit_message(
                content=None,
                embeds=[discord.Embed(description=get_text(uid, "lore_saved"), color=0x4b0082), _v.list_embed()],
                view=_v,
            )
        else:
            entries = gd["lore"][cat]
            if self.edit_index is not None:
                entries[self.edit_index] = text
            else:
                entries.append(text)
            save_json(DATA_FILE, library_data)
            _v = LoreListView(self.user, cat)
            await interaction.response.edit_message(
                content=None,
                embeds=[discord.Embed(description=get_text(uid, "lore_saved"), color=0x4b0082), _v.list_embed()],
                view=_v,
            )


class LoreListView(UserOnlyView):
    def __init__(self, user, category, selected_idx=None):
        super().__init__(user, timeout=300)
        self.category     = category
        self.selected_idx = selected_idx
        uid = user.id
        entries = self.gdata["lore"][category]

        if entries:
            options = [
                discord.SelectOption(
                    label=f"#{i+1}  {e[:80]}",
                    value=str(i),
                    default=(i == selected_idx),
                )
                for i, e in enumerate(entries[:25])
            ]
            sel = discord.ui.Select(placeholder="Chọn mục...", options=options, row=0)
            async def sel_cb(interaction: discord.Interaction):
                idx = int(sel.values[0])
                _v  = LoreListView(self.user, category, selected_idx=idx)
                await interaction.response.edit_message(embeds=[_v.list_embed()], view=_v)
            sel.callback = sel_cb
            self.add_item(sel)

        add_btn = discord.ui.Button(label=get_text(uid, "btn_add_lore"), style=discord.ButtonStyle.success, row=1)
        async def add_cb(interaction: discord.Interaction):
            modal = LoreTextModal(self.user, self.gdata, category)
            await interaction.response.send_modal(modal)
        add_btn.callback = add_cb
        self.add_item(add_btn)

        edit_btn = discord.ui.Button(
            label=get_text(uid, "btn_edit_lore"),
            style=discord.ButtonStyle.primary,
            row=1,
            disabled=(selected_idx is None),
        )
        async def edit_cb(interaction: discord.Interaction):
            modal = LoreTextModal(self.user, self.gdata, category, edit_index=self.selected_idx)
            await interaction.response.send_modal(modal)
        edit_btn.callback = edit_cb
        self.add_item(edit_btn)

        del_btn = discord.ui.Button(
            label=get_text(uid, "btn_del_lore"),
            style=discord.ButtonStyle.danger,
            row=1,
            disabled=(selected_idx is None),
        )
        async def del_cb(interaction: discord.Interaction):
            entries = self.gdata["lore"][category]
            if len(entries) <= 1:
                await interaction.response.send_message(get_text(self.user.id, "lore_min_warn"), ephemeral=True)
                return
            entries.pop(self.selected_idx)
            save_json(DATA_FILE, library_data)
            _v = LoreListView(self.user, category)
            await interaction.response.edit_message(
                content=None,
                embeds=[discord.Embed(description=get_text(self.user.id, "lore_deleted"), color=0x4b0082), _v.list_embed()],
                view=_v,
            )
        del_btn.callback = del_cb
        self.add_item(del_btn)

        back_btn = discord.ui.Button(label=get_text(uid, "btn_back"), style=discord.ButtonStyle.secondary, row=2)
        async def back_cb(interaction: discord.Interaction):
            _lm = LoreMenuView(self.user)
            await interaction.response.edit_message(embeds=[_lm.menu_embed()], view=_lm)
        back_btn.callback = back_cb
        self.add_item(back_btn)
        self.add_item(HomeButton(self.user, row=2))

    def list_embed(self):
        uid     = self.user.id
        cat     = self.category
        entries = self.gdata["lore"][cat]
        titles  = {"library": "📜 Lore thư viện", "librarian": "👻 Lore thủ thư"}
        embed   = discord.Embed(title=titles.get(cat, cat), color=0x4b0082)
        embed.set_author(name="📜 Thư Viện Cổ 📜")
        if not entries:
            embed.description = get_text(uid, "lore_empty")
        else:
            lines = []
            for i, e in enumerate(entries):
                preview  = e[:120].replace("\n", " ")
                selected = " ◄" if i == self.selected_idx else ""
                lines.append(f"**#{i+1}**{selected}\n{preview}{'…' if len(e) > 120 else ''}")
            embed.description = "\n\n".join(lines)
        return embed


class GreetingListView(UserOnlyView):
    def __init__(self, user, category, selected_idx=None):
        super().__init__(user, timeout=300)
        self.category     = category
        self.selected_idx = selected_idx
        uid = user.id
        bucket = self.gdata["lore"][category]
        msgs   = bucket["messages"]
        active = bucket.get("active")

        if msgs:
            options = [
                discord.SelectOption(
                    label=("★ " if i == active else "") + f"#{i+1}  {m[:75]}",
                    value=str(i),
                    default=(i == selected_idx),
                )
                for i, m in enumerate(msgs[:25])
            ]
            sel = discord.ui.Select(placeholder="Chọn lời chào...", options=options, row=0)
            async def sel_cb(interaction: discord.Interaction):
                idx = int(sel.values[0])
                _v  = GreetingListView(self.user, category, selected_idx=idx)
                await interaction.response.edit_message(embeds=[_v.list_embed()], view=_v)
            sel.callback = sel_cb
            self.add_item(sel)

        add_btn = discord.ui.Button(label=get_text(uid, "btn_add_lore"), style=discord.ButtonStyle.success, row=1)
        async def add_cb(interaction: discord.Interaction):
            modal = LoreTextModal(self.user, self.gdata, category, is_greeting=True)
            await interaction.response.send_modal(modal)
        add_btn.callback = add_cb
        self.add_item(add_btn)

        set_active_btn = discord.ui.Button(
            label=get_text(uid, "btn_set_active"),
            style=discord.ButtonStyle.primary,
            row=1,
            disabled=(selected_idx is None),
        )
        async def set_active_cb(interaction: discord.Interaction):
            self.gdata["lore"][category]["active"] = self.selected_idx
            save_json(DATA_FILE, library_data)
            _v = GreetingListView(self.user, category, selected_idx=self.selected_idx)
            await interaction.response.edit_message(
                content=None,
                embeds=[discord.Embed(description=get_text(self.user.id, "lore_active_set"), color=0x4b0082), _v.list_embed()],
                view=_v,
            )
        set_active_btn.callback = set_active_cb
        self.add_item(set_active_btn)

        edit_btn = discord.ui.Button(
            label=get_text(uid, "btn_edit_lore"),
            style=discord.ButtonStyle.secondary,
            row=1,
            disabled=(selected_idx is None),
        )
        async def edit_cb(interaction: discord.Interaction):
            modal = LoreTextModal(self.user, self.gdata, category, edit_index=self.selected_idx, is_greeting=True)
            await interaction.response.send_modal(modal)
        edit_btn.callback = edit_cb
        self.add_item(edit_btn)

        del_btn = discord.ui.Button(
            label=get_text(uid, "btn_del_lore"),
            style=discord.ButtonStyle.danger,
            row=2,
            disabled=(selected_idx is None),
        )
        async def del_cb(interaction: discord.Interaction):
            bucket2 = self.gdata["lore"][category]
            msgs2   = bucket2["messages"]
            if len(msgs2) <= 1:
                await interaction.response.send_message(get_text(self.user.id, "lore_min_warn"), ephemeral=True)
                return
            msgs2.pop(self.selected_idx)
            cur_active = bucket2.get("active")
            if cur_active is not None:
                if cur_active == self.selected_idx:
                    bucket2["active"] = 0
                elif cur_active > self.selected_idx:
                    bucket2["active"] = cur_active - 1
            save_json(DATA_FILE, library_data)
            _v = GreetingListView(self.user, category)
            await interaction.response.edit_message(
                content=None,
                embeds=[discord.Embed(description=get_text(self.user.id, "lore_deleted"), color=0x4b0082), _v.list_embed()],
                view=_v,
            )
        del_btn.callback = del_cb
        self.add_item(del_btn)

        back_btn = discord.ui.Button(label=get_text(uid, "btn_back"), style=discord.ButtonStyle.secondary, row=2)
        async def back_cb(interaction: discord.Interaction):
            _lm = LoreMenuView(self.user)
            await interaction.response.edit_message(embeds=[_lm.menu_embed()], view=_lm)
        back_btn.callback = back_cb
        self.add_item(back_btn)
        self.add_item(HomeButton(self.user, row=2))

    def list_embed(self):
        uid    = self.user.id
        cat    = self.category
        bucket = self.gdata["lore"][cat]
        msgs   = bucket["messages"]
        active = bucket.get("active")
        titles = {"welcome": "👋 Lời chào mở đầu", "farewell": "🌕 Lời tạm biệt"}
        embed  = discord.Embed(title=titles.get(cat, cat), color=0x4b0082)
        embed.set_author(name="📜 Thư Viện Cổ 📜")
        if not msgs:
            embed.description = get_text(uid, "lore_empty")
        else:
            lines = []
            for i, m in enumerate(msgs):
                star    = "★ **[Đang dùng]**  " if i == active else ""
                preview = m[:120].replace("\n", " ")
                sel_mk  = " ◄" if i == self.selected_idx else ""
                lines.append(f"**#{i+1}**{sel_mk}  {star}\n{preview}{'…' if len(m) > 120 else ''}")
            embed.description = "\n\n".join(lines)
        return embed


class LoreMenuView(UserOnlyView):
    def __init__(self, user):
        super().__init__(user, timeout=300)
        uid = user.id
        for label, category, kind in [
            (get_text(uid, "lore_library_btn"),   "library",   "list"),
            (get_text(uid, "lore_librarian_btn"), "librarian", "list"),
            (get_text(uid, "lore_welcome_btn"),   "welcome",   "greet"),
            (get_text(uid, "lore_farewell_btn"),  "farewell",  "greet"),
        ]:
            btn = discord.ui.Button(label=label, style=discord.ButtonStyle.primary, row=0)
            def make_cb(cat, k):
                async def cb(interaction: discord.Interaction):
                    if k == "list":
                        _v = LoreListView(self.user, cat)
                        await interaction.response.edit_message(embeds=[_v.list_embed()], view=_v)
                    else:
                        _v = GreetingListView(self.user, cat)
                        await interaction.response.edit_message(embeds=[_v.list_embed()], view=_v)
                return cb
            btn.callback = make_cb(category, kind)
            self.add_item(btn)

        back_btn = discord.ui.Button(label=get_text(uid, "btn_back"), style=discord.ButtonStyle.secondary, row=1)
        async def back_cb(interaction: discord.Interaction):
            _ap = AdminPanelView(self.user)
            await interaction.response.edit_message(embeds=[_ap.panel_embed()], view=_ap)
        back_btn.callback = back_cb
        self.add_item(back_btn)
        self.add_item(HomeButton(self.user, row=1))

    def menu_embed(self):
        uid = self.user.id
        embed = discord.Embed(title=get_text(uid, "lore_menu_title"), color=0x4b0082)
        embed.set_author(name="📜 Thư Viện Cổ 📜")
        embed.description = (
            "📜 **Lore thư viện** — Câu trả lời khi user hỏi về thư viện (random 1 câu)\n"
            "👻 **Lore thủ thư** — Câu trả lời khi user hỏi về nhân vật (random 1 câu)\n"
            "👋 **Lời chào mở đầu** — Hiển thị khi chạy `/ghostlibrary` (admin chọn 1 câu)\n"
            "🌕 **Lời tạm biệt** — Hiển thị khi user bấm Thoát (admin chọn 1 câu)"
        )
        return embed


@bot.tree.command(name="ghostlibrary", description="Mở giao diện thư viện ma")
async def ghostlibrary(interaction: discord.Interaction):
    _gd   = get_guild_data(interaction.guild.id) if interaction.guild else {}
    _lang = get_lang(interaction.user.id)
    embed = librarian_embed(get_welcome_text(_gd, _lang))
    if (
        interaction.guild
        and isinstance(interaction.user, discord.Member)
        and is_admin_member(interaction.user)
    ):
        embed.add_field(
            name="⚙️ Admin",
            value="Nhấn nút **⚙️ Admin** trong menu chính để quản lý role Cấm thư và xoá nội dung.",
            inline=False,
        )

    await interaction.response.send_message(
        embed=embed,
        view=MainMenuView(interaction.user),
        ephemeral=True,
    )




@bot.tree.command(
    name="pickrole_forbiddenbooks", description="Admin: chọn role được đọc Cấm thư"
)
@app_commands.describe(role="Role được phép đọc Cấm thư")
async def pickrole_forbiddenbooks(interaction: discord.Interaction, role: discord.Role):
    if (
        not interaction.guild
        or not isinstance(interaction.user, discord.Member)
        or not is_admin_member(interaction.user)
    ):
        await interaction.response.send_message(
            get_text(interaction.user.id, "admin_only"), ephemeral=True
        )
        return

    gd = get_guild_data(interaction.guild.id)
    gd["config"]["forbidden_role"] = role.id
    save_json(DATA_FILE, library_data)

    await interaction.response.send_message(
        f"✅ {get_text(interaction.user.id, 'picked_role')} `{role.name}`",
        ephemeral=True,
    )

@bot.event
async def on_command_error(ctx, error):
    print(f"ERROR: {error}")
    await ctx.send("⚠️ Error occurred. Check logs.")
    
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    if message.author.id in drafts and message.attachments:
        expected_channel = draft_message_map.get(message.author.id)

        if expected_channel is not None and message.channel.id != expected_channel:
            await bot.process_commands(message)
            return

        if len(message.attachments) != 1:
            await message.channel.send(
                "Chỉ được gửi đúng 1 ảnh minh họa.", delete_after=10
            )
            await bot.process_commands(message)
            return

        attachment = message.attachments[0]

        if not attachment.content_type or not attachment.content_type.startswith(
            "image/"
        ):
            await message.channel.send("File gửi lên không phải ảnh.", delete_after=10)
            await bot.process_commands(message)
            return

        if attachment.size > MAX_IMAGE_SIZE:
            await message.channel.send(
                get_text(message.author.id, "too_large"), delete_after=10
            )
            await bot.process_commands(message)
            return

        drafts[message.author.id]["image_url"] = attachment.url
        drafts[message.author.id]["image_name"] = attachment.filename
        await message.channel.send(
            get_text(message.author.id, "attach_saved"), delete_after=10
        )

    await bot.process_commands(message)


@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    try:
        synced = await bot.tree.sync()
        print(f"🔁 Synced {len(synced)} slash commands")
    except Exception as e:
        print(f"❌ Sync error: {e}")

@bot.command()
async def ping(ctx):
    await ctx.send("pong 🏓")

import os
TOKEN = os.getenv("TOKEN")

if not TOKEN:
    raise ValueError("❌ TOKEN not found")

bot.run(TOKEN)
