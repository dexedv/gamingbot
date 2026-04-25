import asyncio
import os
import random
import sqlite3

import discord
from discord.ext import commands

QUIZ_CHANNEL_ID = 1494663152569417800
REWARD          = 20      # Äpfel pro richtiger Antwort
HINT_COST       = 100     # Äpfel für einen Tipp
SKIP_COST       = 50      # Äpfel für Aufgabe überspringen

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'gamingbot.db')


# ── DB-Helfer ─────────────────────────────────────────────────────────────────

def _ensure_user(user_id: int, username: str):
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT OR IGNORE INTO users (user_id, username, coins) VALUES (?, ?, 500)",
        (user_id, username),
    )
    conn.commit()
    conn.close()


def _get_aepfel(user_id: int) -> int:
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute("SELECT aepfel FROM users WHERE user_id = ?", (user_id,)).fetchone()
    conn.close()
    return row[0] if row else 0


def _add_aepfel(user_id: int, amount: int):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE users SET aepfel = aepfel + ? WHERE user_id = ?", (amount, user_id))
    conn.commit()
    conn.close()


def _spend_aepfel(user_id: int, amount: int) -> bool:
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute("SELECT aepfel FROM users WHERE user_id = ?", (user_id,)).fetchone()
    if not row or row[0] < amount:
        conn.close()
        return False
    conn.execute("UPDATE users SET aepfel = aepfel - ? WHERE user_id = ?", (amount, user_id))
    conn.commit()
    conn.close()
    return True


# ── Quiz-Daten ────────────────────────────────────────────────────────────────
# Format: ("emoji(s)", "antwort")  — Groß-/Kleinschreibung egal beim Raten

QUIZ_DATA = [
    # ── Tiere ──────────────────────────────────────────────────────────────
    ("🐶", "hund"),
    ("🐱", "katze"),
    ("🐭", "maus"),
    ("🐹", "hamster"),
    ("🐰", "hase"),
    ("🦊", "fuchs"),
    ("🐻", "bär"),
    ("🐼", "panda"),
    ("🐨", "koala"),
    ("🐯", "tiger"),
    ("🦁", "löwe"),
    ("🐮", "kuh"),
    ("🐷", "schwein"),
    ("🐸", "frosch"),
    ("🐵", "affe"),
    ("🐔", "huhn"),
    ("🐧", "pinguin"),
    ("🐦", "vogel"),
    ("🦆", "ente"),
    ("🦅", "adler"),
    ("🦉", "eule"),
    ("🦇", "fledermaus"),
    ("🐺", "wolf"),
    ("🐗", "wildschwein"),
    ("🐴", "pferd"),
    ("🦄", "einhorn"),
    ("🐝", "biene"),
    ("🦋", "schmetterling"),
    ("🐌", "schnecke"),
    ("🐞", "marienkäfer"),
    ("🐜", "ameise"),
    ("🕷️", "spinne"),
    ("🐢", "schildkröte"),
    ("🐍", "schlange"),
    ("🦎", "eidechse"),
    ("🐊", "krokodil"),
    ("🐳", "wal"),
    ("🐬", "delfin"),
    ("🦈", "hai"),
    ("🐙", "tintenfisch"),
    ("🦑", "kalmar"),
    ("🦐", "garnele"),
    ("🦞", "hummer"),
    ("🦀", "krabbe"),
    ("🐡", "kugelfisch"),
    ("🐠", "clownfisch"),
    ("🐟", "fisch"),
    ("🐆", "leopard"),
    ("🦓", "zebra"),
    ("🦍", "gorilla"),
    ("🐘", "elefant"),
    ("🦏", "nashorn"),
    ("🦛", "nilpferd"),
    ("🦒", "giraffe"),
    ("🦌", "hirsch"),
    ("🐐", "ziege"),
    ("🐑", "schaf"),
    ("🦙", "lama"),
    ("🐪", "kamel"),
    ("🦘", "känguru"),
    ("🦥", "faultier"),
    ("🦦", "otter"),
    ("🦨", "stinktier"),
    ("🦡", "dachs"),
    ("🐁", "maus"),
    ("🐀", "ratte"),
    ("🦔", "igel"),
    ("🦃", "truthahn"),
    ("🦚", "pfau"),
    ("🦜", "papagei"),
    ("🦢", "schwan"),
    ("🦩", "flamingo"),
    ("🕊️", "taube"),
    ("🦭", "robbe"),
    ("🐩", "pudel"),
    ("🐓", "hahn"),
    ("🐿️", "eichhörnchen"),
    ("🐂", "stier"),
    ("🐃", "büffel"),
    ("🦬", "bison"),
    ("🐄", "kuh"),
    ("🐎", "pferd"),
    ("🐖", "schwein"),
    ("🐏", "widder"),
    ("🪲", "käfer"),
    ("🪳", "kakerlake"),
    ("🪰", "fliege"),
    ("🪱", "wurm"),
    ("🦟", "mücke"),
    ("🦗", "grille"),
    ("🐇", "hase"),
    ("🦂", "skorpion"),
    ("🦕", "dinosaurier"),
    ("🦖", "tyrannosaurus"),
    ("🐉", "drache"),
    ("🐲", "drache"),

    # ── Essen & Trinken ────────────────────────────────────────────────────
    ("🍎", "apfel"),
    ("🍊", "orange"),
    ("🍋", "zitrone"),
    ("🍇", "trauben"),
    ("🍓", "erdbeere"),
    ("🍒", "kirsche"),
    ("🍑", "pfirsich"),
    ("🍍", "ananas"),
    ("🥭", "mango"),
    ("🍌", "banane"),
    ("🍉", "wassermelone"),
    ("🍈", "melone"),
    ("🥝", "kiwi"),
    ("🍐", "birne"),
    ("🫐", "heidelbeere"),
    ("🍅", "tomate"),
    ("🥕", "karotte"),
    ("🌽", "mais"),
    ("🥦", "brokkoli"),
    ("🥬", "salat"),
    ("🥒", "gurke"),
    ("🫑", "paprika"),
    ("🥑", "avocado"),
    ("🧅", "zwiebel"),
    ("🧄", "knoblauch"),
    ("🥔", "kartoffel"),
    ("🍠", "süßkartoffel"),
    ("🥐", "croissant"),
    ("🍞", "brot"),
    ("🥖", "baguette"),
    ("🧀", "käse"),
    ("🥚", "ei"),
    ("🍳", "spiegelei"),
    ("🥞", "pfannkuchen"),
    ("🧇", "waffel"),
    ("🥓", "speck"),
    ("🌭", "hotdog"),
    ("🍔", "burger"),
    ("🍟", "pommes"),
    ("🍕", "pizza"),
    ("🌮", "taco"),
    ("🌯", "wrap"),
    ("🥙", "kebab"),
    ("🍱", "bento"),
    ("🍜", "nudelsuppe"),
    ("🍝", "spaghetti"),
    ("🍛", "curry"),
    ("🍲", "eintopf"),
    ("🍣", "sushi"),
    ("🍤", "garnelenspieß"),
    ("🍦", "softeis"),
    ("🍧", "sorbet"),
    ("🍨", "eiscreme"),
    ("🍰", "torte"),
    ("🎂", "geburtstagskuchen"),
    ("🧁", "muffin"),
    ("🍩", "donut"),
    ("🍪", "keks"),
    ("🍫", "schokolade"),
    ("🍬", "bonbon"),
    ("🍭", "lutscher"),
    ("🍮", "pudding"),
    ("🧃", "saft"),
    ("🥤", "softdrink"),
    ("☕", "kaffee"),
    ("🍵", "tee"),
    ("🍺", "bier"),
    ("🥂", "sekt"),
    ("🍷", "wein"),
    ("🍸", "cocktail"),
    ("🥃", "whisky"),
    ("🥛", "milch"),
    ("🧋", "bubble tea"),
    ("🫖", "teekanne"),
    ("🍾", "champagner"),
    ("🥜", "erdnuss"),
    ("🌰", "kastanie"),
    ("🫘", "bohne"),
    ("🥯", "bagel"),
    ("🥗", "salat"),
    ("🧆", "falafel"),
    ("🥨", "brezel"),
    ("🍙", "reisball"),
    ("🍚", "reis"),
    ("🍘", "reiskeks"),
    ("🥮", "mondkuchen"),
    ("🧈", "butter"),
    ("🫕", "fondue"),
    ("🫔", "tamale"),
    ("🥫", "konserve"),
    ("🧂", "salz"),
    ("🫙", "einmachglas"),

    # ── Natur & Wetter ─────────────────────────────────────────────────────
    ("⛅", "bewölkt"),
    ("🌧️", "regen"),
    ("⛈️", "gewitter"),
    ("🌩️", "blitz"),
    ("🌨️", "schneefall"),
    ("❄️", "schneeflocke"),
    ("☃️", "schneemann"),
    ("🌬️", "wind"),
    ("🌀", "wirbelsturm"),
    ("🌈", "regenbogen"),
    ("☁️", "wolke"),
    ("⚡", "blitz"),
    ("🌊", "welle"),
    ("🏔️", "berg"),
    ("🌋", "vulkan"),
    ("🏝️", "insel"),
    ("🏜️", "wüste"),
    ("🌵", "kaktus"),
    ("🌴", "palme"),
    ("🌲", "tannenbaum"),
    ("🌳", "baum"),
    ("🌱", "setzling"),
    ("🌿", "blatt"),
    ("🍀", "kleeblatt"),
    ("🌺", "blume"),
    ("🌸", "kirschblüte"),
    ("🌼", "gänseblümchen"),
    ("🌻", "sonnenblume"),
    ("🌹", "rose"),
    ("🌷", "tulpe"),
    ("🌾", "getreide"),
    ("🍁", "ahornblatt"),
    ("🍂", "herbstblatt"),
    ("🍃", "blätter"),
    ("🍄", "pilz"),
    ("🪨", "stein"),
    ("🌍", "erde"),
    ("☀️", "sonne"),
    ("🌙", "mond"),
    ("⭐", "stern"),
    ("💫", "funkelstern"),
    ("☄️", "komet"),
    ("🌕", "vollmond"),
    ("🌑", "neumond"),
    ("🌊", "ozean"),
    ("🏞️", "landschaft"),
    ("🌄", "sonnenaufgang"),
    ("🌅", "sonnenuntergang"),
    ("🪸", "koralle"),
    ("🌫️", "nebel"),
    ("🌡️", "thermometer"),
    ("🌤️", "sonnig"),
    ("🌥️", "bewölkt"),
    ("🌦️", "regenschauer"),
    ("⛄", "schneemann"),
    ("🏔️", "gebirge"),
    ("🗻", "fujisan"),
    ("🏕️", "camping"),
    ("🌃", "nachtstadt"),
    ("🌆", "stadtsonnenuntergang"),

    # ── Fahrzeuge ──────────────────────────────────────────────────────────
    ("🚗", "auto"),
    ("🚙", "geländewagen"),
    ("🚕", "taxi"),
    ("🚌", "bus"),
    ("🚐", "minibus"),
    ("🚑", "krankenwagen"),
    ("🚒", "feuerwehrauto"),
    ("🚓", "polizeiauto"),
    ("🏎️", "rennauto"),
    ("🛻", "pickup"),
    ("🚚", "lastwagen"),
    ("🚛", "lkw"),
    ("🚜", "traktor"),
    ("🏍️", "motorrad"),
    ("🛵", "moped"),
    ("🚲", "fahrrad"),
    ("🛴", "tretroller"),
    ("🛹", "skateboard"),
    ("🚁", "hubschrauber"),
    ("🛸", "ufo"),
    ("✈️", "flugzeug"),
    ("🛩️", "kleinflugzeug"),
    ("🚀", "rakete"),
    ("⛵", "segelboot"),
    ("🚤", "motorboot"),
    ("⛴️", "fähre"),
    ("🚢", "schiff"),
    ("🛳️", "kreuzfahrtschiff"),
    ("🚂", "dampflok"),
    ("🚄", "schnellzug"),
    ("🚇", "u-bahn"),
    ("🚊", "straßenbahn"),
    ("🚝", "einschienenbahn"),
    ("🚞", "bergbahn"),
    ("🛺", "tuk-tuk"),
    ("🪂", "fallschirm"),
    ("🚠", "seilbahn"),
    ("🚡", "hängebahn"),
    ("🚟", "zahnradbahn"),
    ("🛶", "kanu"),
    ("⛽", "tankstelle"),
    ("🚧", "baustelle"),
    ("🏗️", "kran"),

    # ── Gebäude & Orte ─────────────────────────────────────────────────────
    ("🏠", "haus"),
    ("🏡", "einfamilienhaus"),
    ("🏢", "bürogebäude"),
    ("🏥", "krankenhaus"),
    ("🏦", "bank"),
    ("🏨", "hotel"),
    ("🏪", "laden"),
    ("🏫", "schule"),
    ("🏬", "kaufhaus"),
    ("🏭", "fabrik"),
    ("🏯", "burg"),
    ("🏰", "schloss"),
    ("⛪", "kirche"),
    ("🕌", "moschee"),
    ("🛕", "tempel"),
    ("🕍", "synagoge"),
    ("⛲", "brunnen"),
    ("🗼", "eiffelturm"),
    ("🗽", "freiheitsstatue"),
    ("🏟️", "stadion"),
    ("🎠", "karussell"),
    ("🎡", "riesenrad"),
    ("🎢", "achterbahn"),
    ("🎪", "zirkuszelt"),
    ("🏖️", "strand"),
    ("🏗️", "baustelle"),
    ("🏘️", "häuser"),
    ("🏙️", "skyline"),
    ("🌉", "brücke"),
    ("🗺️", "karte"),
    ("🗺️", "landkarte"),
    ("⛺", "zelt"),
    ("🏕️", "zeltplatz"),

    # ── Objekte & Alltag ───────────────────────────────────────────────────
    ("📱", "smartphone"),
    ("💻", "laptop"),
    ("🖥️", "computer"),
    ("⌨️", "tastatur"),
    ("🖱️", "maus"),
    ("🖨️", "drucker"),
    ("📷", "kamera"),
    ("📺", "fernseher"),
    ("📻", "radio"),
    ("📞", "telefon"),
    ("☎️", "telefon"),
    ("🔋", "batterie"),
    ("🔌", "stecker"),
    ("💡", "glühbirne"),
    ("🔦", "taschenlampe"),
    ("🕯️", "kerze"),
    ("💰", "geld"),
    ("💵", "dollar"),
    ("💶", "euro"),
    ("💳", "kreditkarte"),
    ("📦", "paket"),
    ("📫", "briefkasten"),
    ("✉️", "brief"),
    ("📧", "email"),
    ("📝", "notiz"),
    ("📖", "buch"),
    ("📚", "bücher"),
    ("📋", "klemmbrett"),
    ("📁", "ordner"),
    ("🗑️", "mülleimer"),
    ("🔒", "schloss"),
    ("🔑", "schlüssel"),
    ("🗝️", "alter schlüssel"),
    ("🔨", "hammer"),
    ("🪓", "axt"),
    ("⛏️", "spitzhacke"),
    ("🛠️", "werkzeug"),
    ("🔧", "schraubenschlüssel"),
    ("🔩", "schraube"),
    ("🪛", "schraubenzieher"),
    ("🔗", "kette"),
    ("🧲", "magnet"),
    ("🪜", "leiter"),
    ("🧰", "werkzeugkasten"),
    ("🪝", "haken"),
    ("🧱", "ziegel"),
    ("🪞", "spiegel"),
    ("🛋️", "sofa"),
    ("🪑", "stuhl"),
    ("🚿", "dusche"),
    ("🛁", "badewanne"),
    ("🧴", "lotion"),
    ("🧹", "besen"),
    ("🧻", "toilettenpapier"),
    ("🧼", "seife"),
    ("🪣", "eimer"),
    ("🧽", "schwamm"),
    ("🪒", "rasierer"),
    ("🧯", "feuerlöscher"),
    ("🪤", "mausefalle"),
    ("🪚", "säge"),
    ("🧲", "magnet"),
    ("🔬", "mikroskop"),
    ("🔭", "teleskop"),
    ("🧪", "reagenzglas"),
    ("🧫", "petrischale"),
    ("🧬", "dns"),
    ("💉", "spritze"),
    ("💊", "pille"),
    ("🩹", "pflaster"),
    ("🩺", "stethoskop"),
    ("🩻", "röntgenbild"),
    ("🩼", "krücke"),
    ("🎈", "luftballon"),
    ("🎁", "geschenk"),
    ("🎀", "schleife"),
    ("🎉", "konfetti"),
    ("🎊", "partyball"),
    ("🎆", "feuerwerk"),
    ("🎇", "wunderkerze"),
    ("🧨", "böller"),
    ("🎏", "wimpel"),
    ("🎎", "puppe"),
    ("🎍", "bambus"),
    ("🎋", "wunschbaum"),
    ("🎄", "weihnachtsbaum"),
    ("🎃", "kürbis"),
    ("🎑", "erntedankfest"),
    ("🧧", "rotes kuvert"),
    ("🎫", "ticket"),
    ("🎟️", "eintrittskarte"),
    ("🏷️", "preisschild"),
    ("🔮", "kristallkugel"),

    # ── Sport ──────────────────────────────────────────────────────────────
    ("⚽", "fußball"),
    ("🏀", "basketball"),
    ("🏈", "american football"),
    ("⚾", "baseball"),
    ("🎾", "tennis"),
    ("🏸", "badminton"),
    ("🏒", "eishockey"),
    ("🏑", "feldhockey"),
    ("🏓", "tischtennis"),
    ("🏏", "cricket"),
    ("🥊", "boxhandschuh"),
    ("🥋", "kampfsport"),
    ("🏌️", "golf"),
    ("🤺", "fechten"),
    ("🏇", "pferderennen"),
    ("🏋️", "gewichtheben"),
    ("🤸", "turnen"),
    ("🤼", "ringen"),
    ("🤾", "handball"),
    ("🏊", "schwimmen"),
    ("🏄", "surfen"),
    ("🚴", "radfahren"),
    ("🏆", "pokal"),
    ("🥇", "goldmedaille"),
    ("🥈", "silbermedaille"),
    ("🥉", "bronzemedaille"),
    ("🎿", "ski"),
    ("🏂", "snowboard"),
    ("🤿", "tauchen"),
    ("🎣", "angeln"),
    ("🧗", "klettern"),
    ("🤽", "wasserball"),
    ("🚣", "rudern"),
    ("🧘", "yoga"),
    ("🛷", "schlitten"),
    ("⛸️", "schlittschuh"),
    ("🥅", "tor"),
    ("⛳", "golf"),
    ("🎯", "dart"),
    ("🎳", "bowling"),
    ("🎰", "spielautomat"),
    ("🛹", "skateboard"),
    ("🥌", "curlingstein"),
    ("🏹", "bogen"),

    # ── Musik ──────────────────────────────────────────────────────────────
    ("🎵", "note"),
    ("🎶", "noten"),
    ("🎼", "partitur"),
    ("🎤", "mikrofon"),
    ("🎧", "kopfhörer"),
    ("🎷", "saxofon"),
    ("🎸", "gitarre"),
    ("🎹", "klavier"),
    ("🎺", "trompete"),
    ("🎻", "geige"),
    ("🪕", "banjo"),
    ("🥁", "schlagzeug"),
    ("🪘", "trommel"),
    ("🎙️", "studiomikrofon"),
    ("📯", "jagdhorn"),
    ("🪗", "akkordeon"),
    ("🎚️", "mischpult"),
    ("🎛️", "regler"),

    # ── Berufe ─────────────────────────────────────────────────────────────
    ("👨‍⚕️", "arzt"),
    ("👩‍⚕️", "ärztin"),
    ("👨‍🏫", "lehrer"),
    ("👩‍🏫", "lehrerin"),
    ("👨‍🍳", "koch"),
    ("👩‍🍳", "köchin"),
    ("👨‍🔧", "mechaniker"),
    ("👩‍🔧", "mechanikerin"),
    ("👨‍💻", "programmierer"),
    ("👩‍💻", "programmiererin"),
    ("👨‍🎨", "künstler"),
    ("👩‍🎨", "künstlerin"),
    ("👨‍🚒", "feuerwehrmann"),
    ("👩‍🚒", "feuerwehrfrau"),
    ("👨‍✈️", "pilot"),
    ("👩‍✈️", "pilotin"),
    ("👮", "polizist"),
    ("🕵️", "detektiv"),
    ("💂", "wachmann"),
    ("👷", "bauarbeiter"),
    ("🧑‍🔬", "wissenschaftler"),
    ("🧑‍⚖️", "richter"),
    ("🧑‍🌾", "bauer"),
    ("🧑‍🏭", "fabrikarbeiter"),
    ("🧑‍💼", "geschäftsmann"),
    ("🧑‍🎤", "sänger"),
    ("🧑‍🎭", "schauspieler"),
    ("🧑‍🚀", "astronaut"),

    # ── Märchen & Fantasy-Figuren ──────────────────────────────────────────
    ("🧙", "zauberer"),
    ("🧝", "elf"),
    ("🧛", "vampir"),
    ("🧟", "zombie"),
    ("🧞", "dschinn"),
    ("🧜", "meerjungfrau"),
    ("🧚", "fee"),
    ("🧌", "troll"),
    ("🦸", "superheld"),
    ("🦹", "superschurke"),
    ("🤴", "prinz"),
    ("👸", "prinzessin"),
    ("👼", "engel"),
    ("🎅", "weihnachtsmann"),
    ("🤶", "weihnachtsfrau"),
    ("🧑‍🎄", "wichtel"),
    ("🧸", "teddybär"),
    ("🪆", "matroschka"),
    ("🪅", "piñata"),
    ("🤡", "clown"),
    ("👹", "dämon"),
    ("👺", "tengu"),
    ("👻", "geist"),
    ("💀", "totenkopf"),
    ("☠️", "totenkopf mit knochen"),
    ("👽", "alien"),
    ("👾", "space invader"),
    ("🤖", "roboter"),
    ("🎃", "halloween"),

    # ── Emotionen ──────────────────────────────────────────────────────────
    ("😀", "freude"),
    ("😂", "lachen"),
    ("🥹", "gerührt"),
    ("😊", "lächeln"),
    ("😇", "unschuldig"),
    ("🥰", "verliebt"),
    ("😍", "schwärmen"),
    ("😘", "kuss"),
    ("🥳", "feiern"),
    ("😎", "cool"),
    ("🤩", "begeistert"),
    ("😏", "verschmitzt"),
    ("😒", "gelangweilt"),
    ("😞", "enttäuscht"),
    ("😔", "traurig"),
    ("😟", "besorgt"),
    ("😕", "verwirrt"),
    ("😣", "frustriert"),
    ("😫", "erschöpft"),
    ("😩", "müde"),
    ("🥺", "bittend"),
    ("😢", "weinen"),
    ("😭", "schluchzen"),
    ("😤", "wütend"),
    ("😠", "ärgerlich"),
    ("😡", "sehr wütend"),
    ("🤬", "fluchen"),
    ("🤯", "schockiert"),
    ("😳", "verlegen"),
    ("🥵", "überhitzt"),
    ("🥶", "frierend"),
    ("😱", "erschrocken"),
    ("😨", "verängstigt"),
    ("😰", "angstschweißen"),
    ("🤗", "herzlich"),
    ("🤔", "denken"),
    ("🤫", "leise"),
    ("🤐", "schweigen"),
    ("🤨", "skeptisch"),
    ("😐", "neutral"),
    ("😑", "genervt"),
    ("😬", "grimasse"),
    ("🙄", "augenrollen"),
    ("😯", "überrascht"),
    ("😮", "mund offen"),
    ("😲", "erstaunt"),
    ("🥱", "gähnen"),
    ("😴", "schlafen"),
    ("🤤", "sabbern"),
    ("😷", "mundschutz"),
    ("🤒", "fieber"),
    ("🤕", "verletzt"),
    ("🤢", "übelkeit"),
    ("🤮", "erbrechen"),
    ("🤧", "niesen"),
    ("😵", "benommen"),
    ("🤑", "geldgierig"),
    ("🤠", "cowboy"),

    # ── Aktivitäten & Körper ───────────────────────────────────────────────
    ("🏃", "laufen"),
    ("🚶", "gehen"),
    ("🛌", "schlafen"),
    ("🙏", "beten"),
    ("🤝", "handschlag"),
    ("👋", "winken"),
    ("👍", "daumen hoch"),
    ("👎", "daumen runter"),
    ("✌️", "frieden"),
    ("🤞", "gekreuzte finger"),
    ("🤘", "rockzeichen"),
    ("👏", "applaus"),
    ("🙌", "jubeln"),
    ("💪", "muskel"),
    ("👂", "ohr"),
    ("👃", "nase"),
    ("🧠", "gehirn"),
    ("🦷", "zahn"),
    ("🦴", "knochen"),
    ("👁️", "auge"),
    ("👅", "zunge"),
    ("👄", "lippen"),
    ("🤳", "selfie"),
    ("💅", "nagellack"),
    ("🦵", "bein"),
    ("🦶", "fuß"),
    ("🧎", "knien"),
    ("🧍", "stehen"),
    ("🤸", "akrobatik"),
    ("🤼", "kampf"),
    ("🤺", "fechten"),
    ("⛹️", "basketballspieler"),
    ("🏋️", "krafttraining"),
    ("🧗", "klettern"),
    ("🤾", "handballer"),

    # ── Länder (Flaggen) ───────────────────────────────────────────────────
    ("🇩🇪", "deutschland"),
    ("🇫🇷", "frankreich"),
    ("🇮🇹", "italien"),
    ("🇪🇸", "spanien"),
    ("🇵🇹", "portugal"),
    ("🇬🇧", "großbritannien"),
    ("🇺🇸", "usa"),
    ("🇯🇵", "japan"),
    ("🇨🇳", "china"),
    ("🇰🇷", "südkorea"),
    ("🇧🇷", "brasilien"),
    ("🇷🇺", "russland"),
    ("🇦🇺", "australien"),
    ("🇨🇦", "kanada"),
    ("🇲🇽", "mexiko"),
    ("🇮🇳", "indien"),
    ("🇿🇦", "südafrika"),
    ("🇦🇷", "argentinien"),
    ("🇨🇱", "chile"),
    ("🇵🇱", "polen"),
    ("🇳🇱", "niederlande"),
    ("🇧🇪", "belgien"),
    ("🇨🇭", "schweiz"),
    ("🇦🇹", "österreich"),
    ("🇸🇪", "schweden"),
    ("🇳🇴", "norwegen"),
    ("🇩🇰", "dänemark"),
    ("🇫🇮", "finnland"),
    ("🇬🇷", "griechenland"),
    ("🇹🇷", "türkei"),
    ("🇺🇦", "ukraine"),
    ("🇨🇿", "tschechien"),
    ("🇭🇺", "ungarn"),
    ("🇷🇴", "rumänien"),
    ("🇮🇪", "irland"),
    ("🇮🇱", "israel"),
    ("🇪🇬", "ägypten"),
    ("🇲🇦", "marokko"),
    ("🇰🇪", "kenia"),
    ("🇹🇭", "thailand"),
    ("🇻🇳", "vietnam"),
    ("🇮🇩", "indonesien"),
    ("🇵🇭", "philippinen"),
    ("🇵🇰", "pakistan"),
    ("🇲🇾", "malaysia"),
    ("🇸🇬", "singapur"),
    ("🇳🇿", "neuseeland"),
    ("🇮🇷", "iran"),
    ("🇸🇦", "saudi-arabien"),
    ("🇦🇪", "emirate"),
    ("🇶🇦", "katar"),
    ("🇰🇼", "kuwait"),
    ("🇯🇴", "jordanien"),
    ("🇱🇧", "libanon"),
    ("🇨🇴", "kolumbien"),
    ("🇵🇪", "peru"),
    ("🇻🇪", "venezuela"),
    ("🇨🇺", "kuba"),
    ("🇯🇲", "jamaika"),
    ("🇳🇬", "nigeria"),
    ("🇬🇭", "ghana"),
    ("🇪🇹", "äthiopien"),
    ("🇹🇿", "tansania"),
    ("🇺🇬", "uganda"),
    ("🇨🇲", "kamerun"),
    ("🇸🇳", "senegal"),
    ("🇰🇿", "kasachstan"),
    ("🇺🇿", "usbekistan"),
    ("🇧🇬", "bulgarien"),
    ("🇭🇷", "kroatien"),
    ("🇸🇮", "slowenien"),
    ("🇸🇰", "slowakei"),

    # ── Symbole & Zeichen ──────────────────────────────────────────────────
    ("❤️", "herz"),
    ("💔", "gebrochenes herz"),
    ("💕", "zwei herzen"),
    ("💞", "kreisende herzen"),
    ("💓", "schlagendes herz"),
    ("💗", "wachsendes herz"),
    ("💖", "funkelherz"),
    ("💘", "herzpfeil"),
    ("💝", "herzgeschenk"),
    ("🧡", "orange herz"),
    ("💛", "gelbes herz"),
    ("💚", "grünes herz"),
    ("💙", "blaues herz"),
    ("💜", "lila herz"),
    ("🖤", "schwarzes herz"),
    ("🤍", "weißes herz"),
    ("🤎", "braunes herz"),
    ("☮️", "frieden"),
    ("✝️", "kreuz"),
    ("♈", "widder"),
    ("♉", "stier"),
    ("♊", "zwillinge"),
    ("♋", "krebs"),
    ("♌", "löwe"),
    ("♍", "jungfrau"),
    ("♎", "waage"),
    ("♏", "skorpion"),
    ("♐", "schütze"),
    ("♑", "steinbock"),
    ("♒", "wassermann"),
    ("♓", "fische"),
    ("⚠️", "warnung"),
    ("🚫", "verboten"),
    ("❌", "falsch"),
    ("✅", "richtig"),
    ("❓", "frage"),
    ("❗", "ausrufezeichen"),
    ("💯", "hundert"),
    ("🔞", "ab 18"),
    ("📵", "kein handy"),
    ("⛔", "einfahrt verboten"),
    ("🔕", "lautlos"),
    ("🔇", "stummschalten"),
    ("🔈", "lautsprecher"),
    ("🔉", "lautsprecher mittel"),
    ("🔊", "lautsprecher laut"),
    ("📢", "megafon"),
    ("📣", "megafon"),
    ("🔔", "glocke"),
    ("🔕", "glocke stumm"),
    ("🎵", "musik"),
    ("🎶", "musiknoten"),

    # ── Gaming & Technik ───────────────────────────────────────────────────
    ("🎮", "controller"),
    ("🕹️", "joystick"),
    ("👾", "alien"),
    ("🎲", "würfel"),
    ("🃏", "joker"),
    ("♟️", "schach"),
    ("🎯", "dart"),
    ("🎳", "bowling"),
    ("🎰", "spielautomat"),
    ("🧩", "puzzle"),
    ("🪀", "jojo"),
    ("🪁", "steinschleuder"),
    ("🔫", "wasserpistole"),
    ("🎭", "theater"),
    ("🎬", "film"),
    ("🎥", "kamera"),
    ("📽️", "projektor"),
    ("🎞️", "filmstreifen"),
    ("📹", "videokamera"),
    ("📡", "satellit"),
    ("🖥️", "bildschirm"),
    ("🖨️", "drucker"),
    ("⌚", "uhr"),
    ("📡", "antenne"),
    ("🧭", "kompass"),
    ("⏱️", "stoppuhr"),
    ("⏲️", "timer"),
    ("⏰", "wecker"),
    ("🕰️", "standuhr"),
    ("⌛", "sanduhr"),
    ("⏳", "sanduhr"),
    ("🛰️", "satellit"),
    ("🚀", "rakete"),
    ("🌐", "globus"),
    ("🗺️", "weltkarte"),
    ("🧮", "abakus"),
    ("📐", "geodreieck"),
    ("📏", "lineal"),
    ("✏️", "bleistift"),
    ("✒️", "füllfeder"),
    ("🖊️", "kugelschreiber"),
    ("🖋️", "federkiel"),
    ("🖌️", "pinsel"),
    ("🖍️", "wachsmalstift"),
    ("📌", "reißzwecke"),
    ("📍", "pin"),
    ("📎", "büroklammer"),
    ("🖇️", "büroklammern"),
    ("✂️", "schere"),
    ("🗃️", "karteikasten"),
    ("🗄️", "aktenschrank"),

    # ── Emoji-Kombos (Rebus) ───────────────────────────────────────────────
    ("🌊🏄", "surfen"),
    ("⚽🏆", "meisterschaft"),
    ("🎸🔥", "rockstar"),
    ("🏠🔑", "hausschlüssel"),
    ("🐟🥢", "sushi"),
    ("🌙⭐", "sternennacht"),
    ("🦁👑", "löwenkönig"),
    ("🎄🎁", "weihnachten"),
    ("🎂🎉", "geburtstag"),
    ("🍕🍺", "pizzeria"),
    ("☕📰", "morgen"),
    ("🚀🌙", "mondlandung"),
    ("🐝🍯", "honig"),
    ("🐄🥛", "milch"),
    ("🌻☀️", "sonnenblume"),
    ("🎃👻", "halloween"),
    ("❤️💔", "herzschmerz"),
    ("⛵🌊", "segeln"),
    ("🎓📚", "studium"),
    ("🎵🎸", "gitarrenmusik"),
    ("🌹💌", "liebesbrief"),
    ("💍💒", "hochzeit"),
    ("👑💎", "könig"),
    ("🗡️🛡️", "ritter"),
    ("🌋🔥", "vulkanausbruch"),
    ("❄️⛄", "winter"),
    ("🌊🦈", "haiangriff"),
    ("🌴🏖️", "palmenstrand"),
    ("🎡🎢", "freizeitpark"),
    ("🌈☔", "regenbogen"),
    ("🏠🌲", "waldhaus"),
    ("🐺🌕", "werwolf"),
    ("🧛🦇", "vampir"),
    ("🌙💤", "gute nacht"),
    ("🦔🍄", "wald"),
    ("🐸🌧️", "regenwald"),
    ("🦋🌸", "frühling"),
    ("🐝🌺", "bestäubung"),
    ("🦭🌊", "robbe"),
    ("🐋🌊", "wal"),
    ("🌵☀️", "wüste"),
    ("🌲🌲🌲", "wald"),
    ("🏔️❄️", "gletscher"),
    ("🎵🎹", "klaviermusik"),
    ("🏋️💪", "krafttraining"),
    ("🚗🏁", "rennen"),
    ("🎭🎬", "film"),
    ("🎤🎶", "singen"),
    ("🎸🥁", "band"),
    ("🌹🥀", "welke rose"),
    ("🍎📚", "schule"),
    ("🔥💧", "dampf"),
    ("⚡🌩️", "unwetter"),
    ("🌊🏔️", "fjord"),
    ("🐘🎪", "zirkus"),
    ("🦅🌅", "morgenrot"),
    ("🎁🎂", "geburtstagsfest"),
    ("🛒🏪", "einkaufen"),
    ("📚✏️", "lernen"),
    ("🎨🖌️", "malen"),
    ("✂️🧵", "nähen"),
    ("🌙🌙🌙", "mondphasen"),
    ("⭐⭐⭐", "sternenhimmel"),
    ("☀️🌤️", "sonnig"),
    ("🌧️⛈️", "sturm"),
    ("🌺🦋", "blumengarten"),
    ("🎮🛋️", "gaming"),
    ("🤶🎄", "weihnachten"),
    ("🎅🎁", "weihnachtsmann"),
    ("🍺🎸", "konzert"),
    ("🔭⭐", "astronomie"),
    ("🌿🧪", "biologie"),
    ("🦊🌲", "fuchs"),
    ("🐻🍯", "bär und honig"),
    ("🐧❄️", "antarktis"),
    ("🦒🌴", "savanne"),
    ("🐬🌊", "meeresdelfin"),
    ("🦅🏔️", "adler"),
    ("🌸🌸🌸", "kirschblüte"),
    ("🍂🍁", "herbst"),
    ("❄️🌨️", "schneesturm"),
    ("🌊🌊🌊", "meer"),
    ("🔥🔥🔥", "feuersbrunst"),
    ("🌙☁️", "mondnacht"),
    ("⭐🌙", "mondstern"),
    ("🎭🎪", "zirkus"),
    ("🦁🐯", "raubtier"),
    ("🐘🦒", "safari"),
    ("🌴🌺", "tropen"),
    ("🐬🐬", "delfine"),
    ("🌈🌈", "doppelregenbogen"),
    ("🍕🍕", "pizza"),
    ("🚂💨", "dampfzug"),
    ("🌍🌎🌏", "welt"),
    ("🎵🎵🎵", "melodie"),
    ("🏠🏠🏠", "stadt"),
    ("🌲🌲", "wald"),
    ("⚡⚡", "blitzgewitter"),
    ("🔥❄️", "heiß und kalt"),
    ("🌊🔥", "feuer und wasser"),
    ("🏆🥇", "sieger"),
    ("🌹❤️", "lieblingsrose"),
    ("🎤🎧", "musikproduzent"),
    ("📱💬", "chatten"),
    ("🎯🏹", "bogenschütze"),
    ("🧙🔮", "zauberei"),
    ("🏰🤴", "märchenschloss"),
    ("🌙🧛", "vampirnacht"),
    ("🌊🏖️", "küste"),
    ("🐝🌻", "biene auf sonnenblume"),
    ("🎸🎤", "rockkonzert"),
    ("⚔️🛡️", "kampf"),
    ("🔮🌙", "wahrsagerin"),
    ("🌺🌿", "botanik"),
    ("🦁🦓", "savannentiere"),
    ("🐟🐟🐟", "fischschwarm"),
    ("🌸🌸", "kirschblüten"),
    ("🍀🌈", "glück"),
    ("🏄🌊", "wellenreiter"),
    ("🎪🎡", "jahrmarkt"),
    ("🚀⭐", "weltraum"),
    ("🌙🌟", "sternenhimmel"),
    ("☀️🌊", "sonnentag am meer"),
    ("🦋🌼", "schmetterling"),
    ("🍄🌲", "wald"),
    ("🐢🌊", "meeresschildkröte"),
    ("🦈🌊", "tiefsee"),
    ("🌺🌺", "blumenmeer"),
    ("🎵🎶🎵", "musik"),
    ("🏆🎖️", "auszeichnung"),
    ("🌍🛸", "alien invasion"),
    ("⚡🔋", "energie"),
    ("💡🧠", "idee"),
    ("🎨🖼️", "kunstgalerie"),
    ("📚🎓", "bildung"),
    ("🍎🥦", "gesund"),
    ("🏋️🥗", "fitness"),
    ("🎮🏆", "esports"),
    ("🚗🏎️", "autorennen"),
    ("🌊⛵", "segelregatta"),
    ("🎸🎹", "band"),
    ("🥁🎺", "orchester"),
    ("🌹🌷", "blumenstrauß"),
    ("🏠❤️", "zuhause"),
    ("🌟💫", "magie"),
    ("🔥🌊", "dampf"),
    ("⛰️🌲", "bergwald"),
    ("🌙🌃", "nacht"),
    ("☀️🌅", "morgenröte"),
    ("🌊🐠", "korallenriff"),
    ("🦁🌍", "wildnis"),
    ("🎃🕷️", "gruselnacht"),
    ("🌺🦜", "tropisch"),
    ("🐻🌲", "bär im wald"),
    ("🦊🌕", "fuchs bei nacht"),
    ("🐺🌲", "wolf im wald"),
    ("🌸🦋", "frühlingsbote"),
    ("🎄⭐", "weihnachtsstern"),
    ("🌊🐋", "walbeobachtung"),
    ("🦅🌊", "seeadler"),
    ("🎭🎵", "musical"),
    ("🌟🌟🌟", "drei sterne"),
    ("🔥🌟", "feuerwerk"),
    ("💧🌊", "wasser"),
    ("🌵🦂", "wüstentier"),
    ("🦁🦁", "löwenrudel"),
    ("🐧🐧🐧", "pinguinkolonie"),
    ("🎈🎉", "party"),
    ("🌺🌸🌼", "blütenpracht"),
    ("🚀🌍", "raumfahrt"),
    ("🎓🏫", "universität"),
    ("🍕🎮", "gamingabend"),
    ("☕🌅", "morgenkaffe"),
    ("🎸🌟", "rockstar"),
    ("🏄☀️", "strandsurfer"),
    ("🌊🚣", "paddeln"),
    ("🏔️🌨️", "schneeberg"),
    ("🦁🌅", "morgenrot savanne"),
    ("🌴🌊", "insel"),
    ("🐬🐬🐬", "delfinschwarm"),
    ("🦢🌊", "schwan auf see"),
    ("🌸🌿", "japangarten"),
    ("🎋🌙", "bambusnacht"),
    ("🌺🌙", "nachtstimmung"),
    ("🏰🌙", "mondschloss"),
    ("🧝🌲", "elfenwald"),
    ("🧙⭐", "sternenzauberer"),
    ("🦸🦹", "helden vs schurken"),
    ("🌊🌊", "hohe see"),
    ("☀️🏝️", "traumstrand"),
    ("🌈🌈🌈", "regenbogenfarben"),
    ("🎅❄️", "winterweihnacht"),
    ("🍂🌲", "herbstwald"),
    ("🦋🌈", "farbenfroh"),
    ("🌟⭐", "sterne"),
    ("🚂🌉", "zugbrücke"),
    ("🌊🏊", "schwimmen"),
    ("🎪🎠", "jahrmarkt"),
]


# ── Skip-Button ───────────────────────────────────────────────────────────────

class QuizView(discord.ui.View):
    def __init__(self, cog: "EmojiQuizCog"):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(
        label=f"Aufgabe überspringen  (50 🍎)",
        style=discord.ButtonStyle.secondary,
        emoji="⏭️",
    )
    async def skip_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.cog.current:
            await interaction.response.send_message("❌ Keine aktive Frage mehr.", ephemeral=True)
            return

        _ensure_user(interaction.user.id, interaction.user.display_name)
        if not _spend_aepfel(interaction.user.id, SKIP_COST):
            bal = _get_aepfel(interaction.user.id)
            await interaction.response.send_message(
                f"❌ Nicht genug Äpfel! Du hast **{bal}** 🍎, brauchst **{SKIP_COST}** 🍎.",
                ephemeral=True,
            )
            return

        _, answer = self.cog.current
        self.cog.current = None

        # Button deaktivieren
        button.disabled = True
        await interaction.message.edit(view=self)

        bal = _get_aepfel(interaction.user.id)
        await interaction.response.send_message(
            f"⏭️ **{interaction.user.display_name}** hat übersprungen  (−{SKIP_COST} 🍎 · Guthaben: **{bal}** 🍎)\n"
            f"Die Antwort war: **{answer}**"
        )
        asyncio.create_task(self.cog._next_question(3))


# ── Cog ───────────────────────────────────────────────────────────────────────

class EmojiQuizCog(commands.Cog, name="EmojiQuiz"):
    def __init__(self, bot: commands.Bot):
        self.bot      = bot
        self.current  = None   # (emojis, answer) | None
        self._started = False

    # ── Interne Quiz-Logik ────────────────────────────────────────────────

    async def _post_question(self):
        channel = self.bot.get_channel(QUIZ_CHANNEL_ID)
        if not channel:
            return

        self.current = random.choice(QUIZ_DATA)
        emojis, _ = self.current

        embed = discord.Embed(
            title="🎯  Emoji Quiz",
            description=f"## {emojis}",
            color=discord.Color.from_rgb(255, 165, 0),
        )
        embed.set_footer(
            text=f"Tippe die Antwort! · %tipp (−{HINT_COST} 🍎) · %äpfel · +{REWARD} 🍎 bei richtiger Antwort"
        )
        await channel.send(embed=embed, view=QuizView(self))

    async def _next_question(self, delay: int = 5):
        await asyncio.sleep(delay)
        await self._post_question()

    # ── Events ────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_ready(self):
        if not self._started:
            self._started = True
            await asyncio.sleep(3)
            await self._post_question()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        if message.channel.id != QUIZ_CHANNEL_ID:
            return
        if message.content.startswith(('%', '/', '!')):
            return
        if not self.current:
            return

        _, answer = self.current
        if message.content.strip().lower() != answer.lower():
            return

        # Richtige Antwort
        self.current = None

        _ensure_user(message.author.id, message.author.display_name)
        _add_aepfel(message.author.id, REWARD)
        bal = _get_aepfel(message.author.id)

        embed = discord.Embed(
            title="✅  Richtig!",
            description=f"**{message.author.display_name}** hat **{answer}** erraten!",
            color=discord.Color.green(),
        )
        embed.add_field(name="🍎 Belohnung", value=f"+{REWARD} Äpfel", inline=True)
        embed.add_field(name="💰 Guthaben",  value=f"{bal} 🍎",         inline=True)
        await message.channel.send(embed=embed)

        asyncio.create_task(self._next_question(5))

    # ── Commands ──────────────────────────────────────────────────────────

    @commands.command(name="tipp")
    async def hint_cmd(self, ctx: commands.Context):
        """Kaufe einen Tipp für 100 Äpfel — %tipp"""
        if ctx.channel.id != QUIZ_CHANNEL_ID:
            return
        if not self.current:
            await ctx.send("❌ Gerade keine aktive Frage.", delete_after=5)
            return

        _ensure_user(ctx.author.id, ctx.author.display_name)
        if not _spend_aepfel(ctx.author.id, HINT_COST):
            bal = _get_aepfel(ctx.author.id)
            await ctx.send(
                f"❌ Nicht genug Äpfel! Du hast **{bal}** 🍎, brauchst **{HINT_COST}** 🍎.",
                delete_after=8,
            )
            return

        _, answer = self.current
        words = answer.split()
        hint_parts = [w[0] + "＿" * (len(w) - 1) if len(w) > 1 else w for w in words]
        hint = " ".join(hint_parts)

        bal = _get_aepfel(ctx.author.id)
        await ctx.send(
            f"💡 **Tipp** (−{HINT_COST} 🍎 · Guthaben: **{bal}** 🍎)\n"
            f"``{hint}``  ({len(answer)} Zeichen)"
        )

    @commands.command(name="äpfel", aliases=["aepfel", "apfel"])
    async def balance_cmd(self, ctx: commands.Context, member: discord.Member = None):
        """Zeigt dein Äpfel-Guthaben — %äpfel [@nutzer]"""
        target = member or ctx.author
        _ensure_user(target.id, target.display_name)
        bal = _get_aepfel(target.id)
        await ctx.send(f"🍎 **{target.display_name}** hat **{bal} Äpfel**.")

    @commands.command(name="äpfeltop", aliases=["aepfeltop", "quiztop"])
    async def leaderboard_cmd(self, ctx: commands.Context):
        """Top-10 Äpfel-Bestenliste — %äpfeltop"""
        conn = sqlite3.connect(DB_PATH)
        rows = conn.execute(
            "SELECT username, aepfel FROM users ORDER BY aepfel DESC LIMIT 10"
        ).fetchall()
        conn.close()

        if not rows:
            await ctx.send("Noch keine Einträge.")
            return

        medals = ["🥇", "🥈", "🥉"]
        lines  = []
        for i, (username, aepfel) in enumerate(rows):
            prefix = medals[i] if i < 3 else f"`#{i+1}`"
            lines.append(f"{prefix}  **{username}** — {aepfel} 🍎")

        embed = discord.Embed(
            title="🍎  Äpfel-Bestenliste  —  Top 10",
            description="\n".join(lines),
            color=discord.Color.from_rgb(255, 80, 0),
        )
        embed.set_footer(text="Verdiene Äpfel im Emoji-Quiz!")
        await ctx.send(embed=embed)

    @commands.command(name="quizstop", hidden=True)
    async def quiz_stop(self, ctx: commands.Context):
        """Stoppt das Quiz (nur Owner)."""
        if ctx.author.id != 307210134856400908:
            return
        self.current = None
        self._started = False
        await ctx.send("⏹️ Quiz gestoppt.")

    @commands.command(name="quizstart", hidden=True)
    async def quiz_start(self, ctx: commands.Context):
        """Startet das Quiz neu (nur Owner)."""
        if ctx.author.id != 307210134856400908:
            return
        self._started = True
        await self._post_question()
        await ctx.send("▶️ Quiz gestartet.", delete_after=3)


async def setup(bot: commands.Bot):
    await bot.add_cog(EmojiQuizCog(bot))
