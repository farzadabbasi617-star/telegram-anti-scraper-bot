# =================================================================
# 🕵️ Crypto Treasure Hunter Module
# Ethical scanner for public leaked keys / lost wallets
# =================================================================
import os
import json
import time
import random
import re
import io
import csv
import requests
import hashlib

try:
    import base58
    import ecdsa
    HAVE_CRYPTO = True
except:
    HAVE_CRYPTO = False

# ---------------------- BIP39 word list (subset for detection) ----------------------
BIP39_WORDS = {
"abandon","ability","able","about","above","absent","absorb","abstract","absurd","abuse",
"access","accident","account","accuse","achieve","acid","acoustic","acquire","across","act",
"action","actor","actress","actual","adapt","add","addict","address","adjust","admit",
"adult","advance","advice","aerobic","affair","afford","afraid","again","age","agent",
"agree","ahead","aid","air","airport","aisle","alarm","album","alcohol","alert",
"alien","all","alley","allow","almost","alone","alpha","already","also","alter",
"always","amateur","amazing","among","amount","amused","analyst","anchor","ancient","anger",
"angle","angry","animal","ankle","announce","annual","another","answer","antenna","antique",
"anxiety","any","apart","apology","appear","apple","approve","april","arch","arctic",
"area","arena","argue","arm","armed","armor","army","around","arrange","arrest",
"arrive","arrow","art","artefact","artist","artwork","ask","aspect","assault","asset",
"assist","assume","asthma","athlete","atom","attack","attend","attitude","attract","auction",
"audit","august","aunt","author","auto","autumn","average","avocado","avoid","awake",
"award","aware","awesome","awful","awkward","axis","baby","bachelor","bacon","badge",
"bag","balance","balcony","ball","bamboo","banana","banner","bar","barely","bargain",
"barrel","base","basic","basket","battle","beach","bean","beauty","because","become",
"beef","before","begin","behave","behind","believe","below","belt","bench","benefit",
"best","betray","better","between","beyond","bicycle","bid","bike","bind","biology",
"bird","birth","bitter","black","blade","blame","blanket","blast","bleak","bless",
"blind","blood","blossom","blow","blue","blur","blush","board","boat","body",
"boil","bomb","bone","bonus","book","boost","border","boring","borrow","boss",
"bottom","bounce","bound","bowl","box","boy","bracket","brain","brand","brass",
"brave","bread","breeze","brick","bridge","brief","bright","bring","brisk","broken",
"bronze","broom","brother","brown","brush","bubble","buddy","budget","buffalo","build",
"bulb","bulk","bullet","bundle","bunker","burden","burger","burst","bus","business",
"busy","butter","buyer","buzz","cabbage","cabin","cable","cactus","cage","cake",
"call","calm","camera","camp","can","canal","cancel","candy","cannon","canoe",
"canvas","canyon","capable","capital","captain","car","carbon","card","cargo","carpet",
"carry","cart","case","cash","casino","castle","casual","cat","catalog","catch",
"cattle","caught","cause","caution","cave","ceiling","celery","cement","census","century",
"cereal","certain","chair","chalk","champion","change","chaos","chapter","charge","chase",
"cheap","check","cheese","chef","cherry","chest","chicken","chief","child","chimney",
"choice","choose","chronic","chunk","churn","citizen","city","civil","claim","clap",
"clarify","claw","clay","clean","clerk","clever","click","client","cliff","climb",
"clinic","clip","clock","clog","close","cloth","cloud","clown","club","clump",
"cluster","clutch","coach","coast","coconut","code","coffee","coil","coin","collect",
"color","column","combine","come","comfort","comic","common","company","concert","conduct",
"confirm","congress","connect","consider","control","convince","cook","cool","copper","copy",
"coral","core","corn","corner","correct","cost","cotton","couch","country","couple",
"course","cousin","cover","coyote","crack","cradle","craft","cram","crane","crash",
"crawl","crazy","cream","credit","creek","crew","cricket","crime","crisp","critic",
"crop","cross","crouch","crowd","crucial","cruel","cruise","crumble","crush","cry",
"crystal","cube","culture","cup","cupboard","curious","current","curtain","curve","cushion",
"custom","cute","cycle","dad","damage","damp","dance","danger","daring","dash",
"daughter","dawn","day","deal","debate","debris","decade","december","decide","decline",
"decorate","decrease","deer","defense","define","defy","degree","delay","deliver","demand",
"demise","denial","dentist","deny","depart","depend","deposit","depth","deputy","derive",
"describe","desert","design","desk","despair","destroy","detail","detect","develop","device",
"devote","diagram","dial","diamond","diary","dice","diesel","diet","differ","digital",
"dignity","dilemma","dinner","dinosaur","direct","dirt","disagree","discover","disease","dish",
"dismiss","disorder","display","distance","divert","divide","divorce","dizzy","doctor","document",
"dog","doll","dolphin","domain","donate","donkey","donor","door","dose","double",
"dove","draft","dragon","drama","drastic","draw","dream","dress","drift","drill",
"drink","drip","drive","drop","drum","dry","duck","dumb","dune","during",
"dust","dutch","duty","dwarf","dynamic","eager","eagle","early","earn","earth",
"easily","east","easy","echo","ecology","economy","edge","edit","educate","effort",
"egg","eight","either","elbow","elder","electric","elegant","element","elephant","elevator",
"elite","else","embark","embody","embrace","emerge","emotion","employ","empower","empty",
"enable","enact","end","endless","endorse","enemy","energy","enforce","engage","engine",
"enhance","enjoy","enlist","enough","enrich","enroll","ensure","enter","entire","entry",
"envelope","episode","equal","equip","era","erase","erode","erosion","error","erupt",
"escape","essay","essence","estate","eternal","ethics","evidence","evil","evoke","evolve",
"exact","example","excess","exchange","excite","exclude","excuse","execute","exercise","exhaust",
"exhibit","exile","exist","exit","exotic","expand","expect","expire","explain","expose",
"express","extend","extra","eye","eyebrow","fabric","face","faculty","fade","faint",
"faith","fall","false","fame","family","famous","fan","fancy","fantasy","farm",
"fashion","fat","fatal","father","fatigue","fault","favorite","feature","february","federal",
"fee","feed","feel","female","fence","festival","fetch","fever","few","fiber",
"fiction","field","figure","file","film","filter","final","find","fine","finger",
"finish","fire","firm","fiscal","fish","fit","fitness","fix","flag","flame",
"flash","flat","flavor","flee","flexible","flight","flip","float","flock","floor",
"flower","fluid","flush","fly","foam","focus","fog","foil","fold","folk",
"follow","food","foot","force","forest","forget","fork","fortune","forum","forward",
"fossil","foster","found","fox","fragile","frame","frequent","fresh","friend","fringe",
"frog","front","frost","frown","frozen","fruit","fuel","fun","funny","furnace",
"fury","future","gadget","gain","galaxy","gallery","game","gap","garage","garbage",
"garden","garlic","garment","gas","gasp","gate","gather","gauge","gaze","general",
"genius","genre","gentle","genuine","gesture","ghost","giant","gift","giggle","ginger",
"giraffe","girl","give","glad","glance","glare","glass","glide","glimpse","globe",
"gloom","glory","glove","glow","glue","goat","goddess","gold","good","goose",
"gorilla","gospel","gossip","govern","gown","grab","grace","grain","grant","grape",
"grass","gravity","great","green","grid","grief","grit","grocery","group","grow",
"grunt","guard","guess","guide","guilt","guitar","gun","gym","habit","hair",
"half","hammer","hamster","hand","happy","harbor","hard","harsh","harvest","hat",
"have","hawk","hay","hazard","head","health","heart","heavy","hedgehog","height",
"hello","helmet","help","hen","hero","hip","hire","history","hobby","hockey",
"hold","hole","holiday","hollow","home","honey","hood","hope","horn","horror",
"horse","hospital","host","hotel","hour","hover","hub","huge","human","humble",
"humor","hundred","hungry","hunt","hurdle","hurry","hurt","husband","hybrid","ice",
"icon","idea","identify","idle","ignore","ill","illegal","illness","image","imitate",
"immense","immune","impact","impose","improve","impulse","inch","include","income","increase",
"index","indicate","indoor","industry","infant","inflict","inform","initial","inject","inmate",
"inner","innocent","input","inquiry","insane","insect","inside","inspire","install","intact",
"interest","into","invest","invite","involve","iron","island","isolate","issue","item",
"ivory","jacket","jaguar","jar","jazz","jeans","jelly","jewel","job","join",
"joke","journey","joy","judge","juice","jump","jungle","junior","junk","just",
"kangaroo","keen","keep","ketchup","key","kick","kid","kidney","kind","kingdom",
"kiss","kit","kitchen","kite","kitten","kiwi","knee","knife","knock","know",
"lab","label","labor","ladder","lady","lake","lamp","language","laptop","large",
"later","latin","laugh","laundry","lava","law","lawn","lawsuit","layer","lazy",
"leader","leaf","learn","leave","lecture","left","leg","legal","legend","leisure",
"lemon","lend","length","lens","leopard","lesson","letter","level","liberty","library",
"license","life","lift","light","like","limb","limit","link","lion","liquid",
"list","little","live","lizard","load","loan","lobster","local","lock","logic",
"lonely","long","loop","lottery","loud","lounge","love","loyal","lucky","luggage",
"lumber","lunar","lunch","luxury","lyrics","machine","mad","magic","magnet","maid",
"mail","main","major","make","mammal","man","manage","mandate","mango","mansion",
"manual","maple","marble","march","margin","marine","market","marriage","mask","mass",
"master","match","material","math","matrix","matter","maximum","maze","meadow","mean",
"measure","meat","mechanic","medal","media","melody","melt","member","memory","mention",
"menu","mercy","merge","merit","merry","mesh","message","metal","method","middle",
"midnight","milk","million","mimic","mind","minimum","minor","minute","miracle","mirror",
"misery","miss","mistake","mix","mixed","mixture","mobile","model","modify","mom",
"moment","monitor","monkey","monster","month","moon","moral","more","morning","mosquito",
"mother","motion","motor","mountain","mouse","move","movie","much","muffin","mule",
"multiply","muscle","museum","mushroom","music","must","mutual","myself","mystery","myth",
"naive","name","napkin","narrow","nasty","nation","nature","near","neck","need",
"negative","neglect","neither","nephew","nerve","nest","net","network","neutral","never",
"news","next","nice","night","noble","noise","nominee","noodle","normal","north",
"nose","notable","nothing","notice","novel","now","nuclear","number","nurse","nut",
"oak","obey","object","oblige","obscure","observe","obtain","obvious","occur","ocean",
"october","odor","off","offer","office","often","oil","okay","old","olive",
"olympic","omit","once","one","onion","online","only","open","opera","opinion",
"oppose","option","orange","orbit","orchard","order","ordinary","organ","orient","original",
"orphan","ostrich","other","outdoor","outer","output","outside","oval","oven","over",
"own","owner","oxygen","oyster","ozone","pact","paddle","page","pair","palace",
"palm","panda","panel","panic","panther","paper","parade","parent","park","parrot",
"party","pass","patch","path","patient","patrol","pattern","pause","pave","payment",
"peace","peanut","pear","pelican","pen","penalty","pencil","people","pepper","perfect",
"permit","person","pet","phone","photo","phrase","physical","piano","picnic","picture",
"piece","pig","pigeon","pill","pilot","pink","pioneer","pipe","pistol","pitch",
"pizza","place","planet","plastic","plate","play","please","pledge","pluck","plug",
"plunge","poem","poet","point","polar","pole","police","pond","pony","pool",
"popular","portion","position","possible","post","potato","pottery","poverty","powder","power",
"practice","praise","predict","prefer","prepare","present","pretty","prevent","price","pride",
"primary","print","priority","prison","private","prize","problem","process","produce","profit",
"program","project","promote","proof","property","prosper","protect","proud","provide","public",
"pudding","pull","pulp","pulse","pumpkin","punch","pupil","puppy","purchase","purity",
"purpose","purse","push","put","puzzle","pyramid","quality","quantum","quarter","question",
"quick","quit","quiz","quote","rabbit","raccoon","race","rack","radar","radio",
"rage","rail","rain","raise","rally","ramp","ranch","random","range","rapid",
"rare","rate","rather","raven","raw","razor","ready","real","reason","rebel",
"rebuild","recall","receive","recipe","record","recycle","reduce","reflect","reform","refuse",
"region","regret","regular","reject","relax","release","relief","rely","remain","remember",
"remind","remove","render","renew","rent","reopen","repair","repeat","replace","report",
"require","rescue","resemble","resist","resource","response","result","retire","retreat","return",
"reunion","reveal","review","reward","rhythm","rib","ribbon","rice","rich","ride",
"ridge","rifle","right","rigid","ring","riot","ripple","risk","ritual","rival",
"river","road","roast","robot","robust","rocket","romance","roof","rookie","room",
"rose","rotate","rough","round","route","royal","rubber","rude","rug","rule",
"run","runway","rural","sad","saddle","sadness","safe","sail","salad","salmon",
"salon","salt","salute","same","sample","sand","satisfy","satoshi","save","say",
"scale","scan","scare","scatter","scene","scheme","school","science","scissors","scorpion",
"scout","scrap","screen","script","scrub","sea","search","season","seat","second",
"secret","section","security","seed","seek","segment","select","sell","seminar","senior",
"sense","sentence","series","service","session","settle","setup","seven","shadow","shaft",
"shallow","share","shed","shell","sheriff","shield","shift","shine","ship","shiver",
"shock","shoe","shoot","shop","short","shoulder","shove","shrimp","shrug","shuffle",
"shy","sibling","sick","side","siege","sight","sign","silent","silk","silly",
"silver","similar","simple","since","sing","siren","sister","situate","six","size",
"skate","sketch","ski","skill","skin","skirt","skull","slab","slam","sleep",
"slender","slice","slide","slight","slim","slogan","slot","slow","slush","small",
"smart","smile","smoke","smooth","snack","snake","snap","sniff","snow","soap",
"soccer","social","sock","soda","soft","solar","soldier","solid","solution","solve",
"someone","song","soon","sorry","sort","soul","sound","soup","source","south",
"space","spare","spatial","spawn","speak","special","speed","spell","spend","sphere",
"spice","spider","spike","spin","spirit","split","sponsor","spoon","sport","spot",
"spray","spread","spring","spy","square","squeeze","squirrel","stable","stadium","staff",
"stage","stairs","stamp","stand","start","state","stay","steak","steel","stem",
"step","stereo","stick","still","sting","stock","stomach","stone","stool","story",
"stove","strategy","street","strike","strong","struggle","student","stuff","stumble","style",
"subject","submit","subway","success","such","sudden","suffer","sugar","suggest","suit",
"summer","sun","sunny","sunset","super","supply","supreme","sure","surface","surge",
"surprise","surround","survey","suspect","sustain","swallow","swamp","swap","swarm","swear",
"sweet","swim","swing","switch","sword","symbol","symptom","syrup","system","table",
"tackle","tail","talent","talk","tank","tape","target","task","taste","tattoo",
"taxi","teach","team","tell","ten","tenant","tennis","tent","term","test",
"text","thank","that","theme","then","theory","there","they","thing","this",
"thought","three","thrive","throw","thumb","thunder","ticket","tide","tiger","tilt",
"timber","time","tiny","tip","tired","tissue","title","toast","tobacco","today",
"toddler","toe","together","toilet","token","tomato","tomorrow","tone","tongue","tonight",
"tool","tooth","top","topic","topple","torch","tornado","tortoise","toss","total",
"tourist","toward","tower","town","toy","track","trade","traffic","tragic","train",
"transfer","trap","trash","travel","tray","treat","tree","trend","trial","tribe",
"trick","trigger","trim","trip","trophy","trouble","truck","true","truly","trumpet",
"trust","truth","try","tube","tuna","tunnel","turn","turtle","twelve","twenty",
"twice","twin","twist","two","type","typical","ugly","umbrella","unable","unaware",
"uncle","uncover","under","undo","unfair","unfold","unhappy","uniform","union","unique",
"unit","universe","unknown","unlock","until","unusual","unveil","update","upgrade","uphold",
"upon","upper","upset","urban","usage","use","used","useful","useless","usual",
"utility","vacant","vacuum","vague","valid","valley","valve","van","vanish",
"vapor","various","vast","vault","vehicle","velvet","vendor","venture","venue","verb",
"verify","version","very","vessel","veteran","viable","vibrant","vicious","victory","video",
"view","village","vintage","violin","virtual","virus","visa","visit","visual","vital",
"vivid","vocal","voice","void","volcano","volume","vote","voyage","wage","wagon",
"wait","walk","wall","walnut","want","warfare","warm","warrior","wash","wasp",
"waste","water","wave","way","weak","wealth","weapon","wear","weasel","weather",
"web","wedding","weekend","weird","welcome","well","west","wet","whale","what",
"wheat","wheel","when","where","whip","whisper","wide","width","wife","wild",
"will","win","window","wine","wing","wink","winner","winter","wire","wisdom",
"wise","wish","witness","wolf","woman","wonder","wood","wool","word","work",
"world","worry","worth","wrap","wreck","wrestle","wrist","write","wrong","yard",
"year","yellow","you","young","youth","zebra","zero","zone","zoo"
}

import asyncio
import atexit
import threading

# Global auto scanner state
auto_scan_running = False
auto_scan_thread = None

# ---------------------- Auto public scanner ----------------------
def _gist_is_recent(gist, max_age_years=2):
    """Check if a gist is newer than max_age_years"""
    try:
        created = gist.get("created_at", "")
        if not created:
            return True
        # Github date ISO 8601
        y = int(created[:4])
        return y >= (time.gmtime().tm_year - max_age_years)
    except:
        return True

def fetch_recent_pastes():
    """Fetch recent public github gists from last 2 years"""
    results = []
    try:
        headers = {"Accept":"application/vnd.github.v3+json", "User-Agent":"Mozilla/5.0 TreasureHunter/1.0"}
        r = requests.get("https://api.github.com/gists/public?per_page=100", timeout=12, headers=headers)
        if r.ok:
            for gist in r.json():
                if not _gist_is_recent(gist, 2):
                    continue
                for fn, finfo in gist.get("files", {}).items():
                    raw = finfo.get("raw_url")
                    lang = finfo.get("language", "") or ""
                    if raw:
                        # Only check code/text files, skip binaries/images
                        if finfo.get("size",0) and finfo["size"] > 5_000_000:
                            continue
                        try:
                            txt = requests.get(raw, timeout=8, headers=headers).text
                            if isinstance(txt, str) and len(txt) < 1_000_000:
                                results.append((txt, f"gist:{gist['id'][:8]}"))
                        except:
                            pass
    except Exception as e:
        print(f"github scan err: {e}", flush=True)
    return results

async def auto_scanner_loop(bot_app, admin_id):
    """Background task 24/7 to scan public sources - only report items WITH balance"""
    global auto_scan_running
    auto_scan_running = True
    state = load_hunter_state()
    state["running"] = True
    state["started_at"] = int(time.time())
    state["scanned_gists"] = state.get("scanned_gists", 0)
    save_hunter_state(state)
    print("🕵️ Auto treasure scanner started 24/7 - only reporting wallets with balance", flush=True)
    try:
        await bot_app.send_message(admin_id, "✅ <b>اسکنر خودکار حرفه‌ای فعال شد</b>\n\n🔍 فقط گیست‌های عمومی آخر ۲ سال اسکن میشوند\n⚠️ فقط کیف پول‌هایی که موجودی واقعی دارند گزارش میشوند\n❌ کیف پول خالی اصلا نمایش داده نمیشود")
    except:
        pass
    while auto_scan_running:
        try:
            state = load_hunter_state()
            state["checked"] += 1
            sources = fetch_recent_pastes()
            state["scanned_gists"] = state.get("scanned_gists",0) + len(sources)
            save_hunter_state(state)
            existing = load_found()
            seen_keys = set((f["type"], f["value"]) for f in existing)
            reported = 0
            for text, src in sources:
                # Fast pattern pre-filter
                if not any(k in text.lower() for k in ["seed", "mnemonic", "private", "key", "wif", "abandon", "wallet"]):
                    # Quick check for hex/WIF patterns even without keywords
                    if not RE_BTC_WIF.search(text) and not RE_ETH_ADDR.search(text):
                        continue
                findings = scan_text(text, source=src)
                if not findings:
                    continue
                # ONLY check balance for items that look real
                for f in findings:
                    k = (f["type"], f["value"])
                    if k in seen_keys:
                        continue
                    # Skip eth/sol/tron addresses without keys (they are public! everyone knows them)
                    # Only check: seed phrases, BTC WIF private keys (these grant access to money)
                    if f["type"] in ("eth_addr", "btc_addr", "tron_addr", "sol_addr"):
                        # Just addresses are public, no need to report - they can't be used to steal
                        # Unless you have the private key, knowing the address means nothing
                        continue
                # Now check balances only for private keys/seeds
                valid_findings = [f for f in findings if f["type"] in ("seed_phrase", "btc_wif")]
                checked = check_balance_of_findings(valid_findings)
                # Also collect game accounts (no balance check)
                game_findings = [f for f in findings if f["type"] == "game_account"]
                for f in checked:
                    bal = f.get("balance", 0) or 0
                    total = bal
                    if f.get("bnb_balance",0):
                        total += f["bnb_balance"]
                    if total < 0.0001:
                        continue
                    # We found a real wallet with money!
                    existing.append(f)
                    seen_keys.add(k)
                    reported += 1
                    coin = f.get("coin","")
                    val = f["value"]
                    msg = f"🚨 <b>کیف پول با موجودی پیدا شد!</b>\n\n"
                    msg += f"📂 منبع: {src}\n"
                    msg += f"🔑 نوع: {f['type']}\n"
                    msg += f"💰 موجودی: {bal:.8f} {coin}"
                    if f.get("bnb_balance",0) > 0.0001:
                        msg += f"\n+ {f['bnb_balance']:.8f} BNB"
                    msg += f"\n\n🔐 مقدار:\n<code>{val[:700]}</code>"
                    if f.get("derived_addr"):
                        msg += f"\n\n📍 آدرس استخراج شده: <code>{f['derived_addr']}</code>"
                    try:
                        await bot_app.send_message(admin_id, msg)
                    except:
                        pass
                    await asyncio.sleep(1)
                # Send game accounts batch notification
                game_new = 0
                for f in game_findings:
                    gk = (f["type"], f["value"])
                    if gk not in seen_keys:
                        existing.append(f)
                        seen_keys.add(gk)
                        game_new += 1
                if game_new > 0:
                    try:
                        await bot_app.send_message(admin_id, f"🎮 {game_new} کمبو ایمیل:رمز (اکانت بازی/سرویس) در {src} پیدا شد. در لیست ذخیره شد.")
                    except:
                        pass
            if reported > 0:
                save_found(existing)
            # Random wait 2-4 minutes between scans
            wait = random.randint(120, 240)
            await asyncio.sleep(wait)
        except Exception as e:
            print(f"Auto scan error: {e}", flush=True)
            await asyncio.sleep(90)

def start_auto_scanner(app, admin_id):
    """Start the auto scanner in background"""
    global auto_scan_thread
    if not auto_scan_running:
        asyncio.create_task(auto_scanner_loop(app, admin_id))

# ---------------------- Regex patterns ----------------------
RE_BTC_WIF = re.compile(r'(?<![a-zA-Z0-9])[5KL][1-9A-HJ-NP-Za-km-z]{50,51}(?![a-zA-Z0-9])')
RE_TRON_ADDR = re.compile(r'(?<![a-zA-Z0-9])T[1-9A-HJ-NP-Za-km-z]{33}(?![a-zA-Z0-9])')
RE_BTC_ADDR = re.compile(r'(?<![a-zA-Z0-9])[13][a-km-zA-HJ-NP-Z1-9]{25,34}(?![a-zA-Z0-9])|bc1[a-z0-9]{25,60}(?![a-zA-Z0-9])')
RE_ETH_ADDR = re.compile(r'(?<![a-zA-Z0-9])0x[a-fA-F0-9]{40}(?![a-zA-Z0-9])')
RE_SOL_ADDR = re.compile(r'(?<![a-zA-Z0-9])[1-9A-HJ-NP-Za-km-z]{32,44}(?![a-zA-Z0-9])')
# Account / credential patterns for games & logins
RE_EMAIL_PASS = re.compile(r'([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)\s*[:|;,|]\s*([^\s:<>"|]{4,60})')
RE_USER_PASS = re.compile(r'(?<![a-zA-Z0-9])([A-Za-z0-9_.-]{3,25})\s*:\s*([^\s:<>"|]{4,50})')
# Common game / account keywords to identify combo lists
GAME_KEYWORDS = ["clash", "royal", "coc", "pubg", "freefire", "ff", "valorant", "steam", "epic",
                 "minecraft", "lol", "league", "fortnite", "roblox", "genshin", "gta", "rockstar",
                 "riot", "epicgames", "origin", "ubisoft", "battle", "discord",
                 "combo", "cracked", "account", "pass", "login", "user:pass", "email:pass"]

# ---------------------- RPC endpoints ----------------------
BSC_RPC = "https://bsc-dataseed1.binance.org"
ETH_RPC = "https://eth.llamarpc.com"
TRON_RPC = "https://api.trongrid.io"
BTC_API = "https://blockstream.info/api"
SOL_RPC = "https://api.mainnet-beta.solana.com"

FOUND_FILE = "found_treasures.json"
STATE_FILE = "hunter_state.json"

# ---------------------- State helpers ----------------------
def load_found():
    try:
        with open(FOUND_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return []

def save_found(lst):
    with open(FOUND_FILE, "w", encoding="utf-8") as f:
        json.dump(lst, f, ensure_ascii=False, indent=2)

def load_hunter_state():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {"checked": 0, "running": False, "started_at": 0}

def save_hunter_state(s):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False)

# ---------------------- Balance checks ----------------------
def check_btc_balance(address):
    try:
        r = requests.get(f"{BTC_API}/address/{address}", timeout=10)
        if r.ok:
            d = r.json()
            funded = d.get("chain_stats", {}).get("funded_txo_sum", 0)
            spent = d.get("chain_stats", {}).get("spent_txo_sum", 0)
            satoshi = funded - spent
            return satoshi / 100_000_000, "BTC"
    except:
        pass
    return 0, "BTC"

def check_eth_balance(address):
    try:
        payload = {"jsonrpc":"2.0","method":"eth_getBalance","params":[address,"latest"],"id":1}
        r = requests.post(ETH_RPC, json=payload, timeout=10)
        if r.ok:
            bal_hex = r.json().get("result", "0x0")
            wei = int(bal_hex, 16)
            return wei / 1e18, "ETH"
    except:
        pass
    return 0, "ETH"

def check_bsc_balance(address):
    try:
        payload = {"jsonrpc":"2.0","method":"eth_getBalance","params":[address,"latest"],"id":1}
        r = requests.post(BSC_RPC, json=payload, timeout=10)
        if r.ok:
            bal_hex = r.json().get("result", "0x0")
            wei = int(bal_hex, 16)
            return wei / 1e18, "BNB"
    except:
        pass
    return 0, "BNB"

def check_tron_balance(address):
    try:
        r = requests.get(f"{TRON_RPC}/v1/accounts/{address}", timeout=10)
        if r.ok:
            data = r.json().get("data", [])
            if data:
                bal = data[0].get("balance", 0)
                return bal / 1_000_000, "TRX"
    except:
        pass
    return 0, "TRX"

def check_sol_balance(address):
    try:
        payload = {"jsonrpc":"2.0","id":1,"method":"getBalance","params":[address]}
        r = requests.post(SOL_RPC, json=payload, timeout=10)
        if r.ok:
            res = r.json()
            val = res.get("result",{}).get("value",0)
            return val / 1_000_000_000, "SOL"
    except:
        pass
    return 0, "SOL"

def wif_to_btc_address(wif):
    """Convert WIF to BTC P2PKH address"""
    if not HAVE_CRYPTO:
        return None
    try:
        raw = base58.b58decode(wif)
        key = raw[1:-4]
        if len(key) == 33 and key[-1] == 0x01:
            priv = key[:-1]
        elif len(key) == 32:
            priv = key
        else:
            return None
        sk = ecdsa.SigningKey.from_string(priv, curve=ecdsa.SECP256k1)
        vk = sk.get_verifying_key()
        pub_bytes = vk.to_string()
        # compressed public key
        prefix = b'\x02' if (pub_bytes[31] & 1) == 0 else b'\x03'
        pub = prefix + pub_bytes[:32]
        ripemd = hashlib.new('ripemd160')
        ripemd.update(hashlib.sha256(pub).digest())
        h160 = ripemd.digest()
        payload = b'\x00' + h160
        chksum = hashlib.sha256(hashlib.sha256(payload).digest()).digest()[:4]
        return base58.b58encode(payload + chksum).decode()
    except:
        return None

# ---------------------- Seed detection ----------------------
def detect_seed_phrases(text):
    tokens = re.findall(r"[a-zA-Z]+", text.lower())
    seeds = []
    i = 0
    n = len(tokens)
    while i < n:
        matched = False
        for L in (24, 18, 12):
            run = tokens[i:i+L]
            if len(run) < L:
                continue
            if all(w in BIP39_WORDS for w in run):
                seeds.append(" ".join(run))
                i += L
                matched = True
                break
        if not matched:
            i += 1
    return seeds

def detect_game_accounts(text):
    """Detect email:pass or user:pass combos in leaked lists"""
    results = []
    low_text = text.lower()
    has_game_context = any(k in low_text for k in GAME_KEYWORDS) or len(RE_EMAIL_PASS.findall(text)) > 3
    if not has_game_context:
        return results
    # Email:pass combos
    seen = set()
    for mail, pwd in RE_EMAIL_PASS.findall(text):
        if len(pwd) < 4 or len(pwd) > 50:
            continue
        # Skip fake / common placeholders
        if pwd.lower() in ("password", "123456", "your_password", "pass"):
            continue
        key = f"{mail}:{pwd}"
        if key in seen:
            continue
        seen.add(key)
        results.append({
            "type": "game_account", "value": f"{mail}:{pwd}",
            "source": "", "ts": int(time.time()), "balance": None, "status": "found"
        })
    return results

# ---------------------- Main scan function ----------------------
def scan_text(text, source="manual"):
    """Scan text and return list of findings"""
    results = []
    # seeds
    for seed in detect_seed_phrases(text):
        results.append({
            "type": "seed_phrase", "value": seed, "source": source,
            "ts": int(time.time()), "balance": None, "status": "found"
        })
    # BTC WIF
    for w in RE_BTC_WIF.findall(text):
        results.append({
            "type": "btc_wif", "value": w, "source": source,
            "ts": int(time.time()), "balance": None, "status": "found"
        })
    # ETH addresses
    for a in RE_ETH_ADDR.findall(text):
        results.append({
            "type": "eth_addr", "value": a, "source": source,
            "ts": int(time.time()), "balance": None, "status": "found"
        })
    # BTC addresses
    for a in RE_BTC_ADDR.findall(text):
        results.append({
            "type": "btc_addr", "value": a, "source": source,
            "ts": int(time.time()), "balance": None, "status": "found"
        })
    # TRON
    for a in RE_TRON_ADDR.findall(text):
        results.append({
            "type": "tron_addr", "value": a, "source": source,
            "ts": int(time.time()), "balance": None, "status": "found"
        })
    # Game accounts
    results.extend(detect_game_accounts(text))
    return results

def check_balance_of_findings(findings):
    """Check balances for found items and update them. Returns list with balance filled."""
    for f in findings:
        try:
            t = f["type"]
            v = f["value"]
            bal = 0
            coin = ""
            if t == "btc_wif":
                addr = wif_to_btc_address(v)
                if addr:
                    bal, coin = check_btc_balance(addr)
                    f["derived_addr"] = addr
            elif t == "btc_addr":
                bal, coin = check_btc_balance(v)
            elif t == "eth_addr":
                bal, coin = check_eth_balance(v)
                bnb_bal, _ = check_bsc_balance(v)
                f["bnb_balance"] = bnb_bal
            elif t == "tron_addr":
                bal, coin = check_tron_balance(v)
            f["balance"] = bal
            f["coin"] = coin
        except:
            pass
    return findings

def export_found_csv(found):
    out = io.StringIO()
    if found:
        keys = ["type","value","source","ts","balance","coin","status"]
        keys = [k for k in keys]
        w = csv.DictWriter(out, fieldnames=list(found[0].keys()), extrasaction="ignore")
        w.writeheader()
        w.writerows(found)
    return out.getvalue().encode("utf-8-sig")
