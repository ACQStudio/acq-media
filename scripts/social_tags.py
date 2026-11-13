"""Hashtaguri în funcție de subiect, fără apeluri la servicii externe."""

import re
import unicodedata

FALLBACK_TAGS = {
    "sport": ("#Sport", "#SportsNews"),
    "hot": ("#Showbiz", "#Vedete"),
    "news": ("#Stiri", "#Actualitate"),
    "music": ("#Muzica", "#MusicNews"),
}

TOPIC_TAGS = {
    "sport": (
        (r"\bfcsb\b", ("#FCSB", "#SuperLiga", "#FotbalRomanesc")),
        (r"\b(superliga|cfr cluj|universitatea cluj|dinamo bucuresti|rapid bucuresti)\b", ("#SuperLiga", "#FotbalRomanesc")),
        (r"\b(champions league|liga campionilor)\b", ("#ChampionsLeague", "#UCL")),
        (r"\b(premier league|chelsea|arsenal|liverpool|manchester united|aston villa)\b", ("#PremierLeague", "#Football")),
        (r"\b(turneul campioanelor|wta finals)\b", ("#WTAFinals", "#WTA", "#Tennis")),
        (r"\b(jessica pegula|pegula)\b", ("#JessicaPegula", "#WTA")),
        (r"\b(tenis|tenismen\w*|wta|atp)\b", ("#Tennis", "#Tenis")),
        (r"\b(formula ?1|f1|marele premiu)\b", ("#F1", "#Formula1", "#Motorsport")),
        (r"\b(cricket|the ashes)\b", ("#Cricket", "#CricketNews")),
        (r"\b(box|boxer\w*|pugilist\w*)\b", ("#Boxing", "#Box")),
        (r"\b(baschet|nba)\b", ("#Basketball", "#Baschet")),
        (r"\b(rugby)\b", ("#Rugby", "#RugbyNews")),
        (r"\b(fotbal\w*|football|fotbalist\w*)\b", ("#Fotbal", "#Football")),
    ),
    "hot": (
        (r"\basia express\b", ("#AsiaExpress", "#RealityTV")),
        (r"\b(toto dumitrescu|mihai dedu|dana roba)\b", ("#ShowbizRomanesc", "#Vedete")),
        (r"\b(prezentator\w*|emisiun\w*|televiziun\w*)\b", ("#Televiziune", "#TV")),
        (r"\b(actor\w*|actrit\w*|hollywood)\b", ("#Celebrities", "#Entertainment")),
        (r"\b(nunt\w*|casator\w*)\b", ("#Nunta", "#Showbiz")),
        (r"\b(influencer\w*|creator\w* de continut)\b", ("#Influenceri", "#SocialMedia")),
        (r"\b(anchet\w*|procuror\w*|expertiz\w*)\b", ("#Actualitate", "#Justitie")),
        (r"\b(monden\w*|vedet\w*|showbiz)\b", ("#Showbiz", "#Vedete")),
    ),
    "news": (
        (r"\b(bnr|banca nationala|doband\w*|inflati\w*|banca centrala)\b", ("#Inflatie", "#Finante", "#Economie")),
        (r"\b(nvidia)\b", ("#Nvidia", "#Semiconductors", "#ArtificialIntelligence")),
        (r"\b(baidu|ernie)\b", ("#Baidu", "#ArtificialIntelligence", "#TechNews")),
        (r"\b(siemens)\b", ("#Siemens", "#Industrie", "#BusinessNews")),
        (r"\b(ucrain\w*|zelensk\w*)\b", ("#Ucraina", "#Ukraine", "#Geopolitica")),
        (r"\b(aukus)\b", ("#AUKUS", "#Geopolitica", "#Australia")),
        (r"\b(neptun deep|gaze naturale|gaze din marea neagra)\b", ("#Energie", "#GazeNaturale", "#Romania")),
        (r"\b(petrol\w*|brent)\b", ("#Petrol", "#Energie")),
        (r"\b(inteligent\w* artificial\w*|openai|chatgpt|semiconduct\w*)\b", ("#AI", "#TechNews")),
        (r"\b(burs\w*|actiuni|wall street|obligatiun\w*)\b", ("#Bursa", "#Investitii", "#StockMarket")),
        (r"\b(pib|produsul intern brut|economic\w*|economie)\b", ("#Economie", "#Economy")),
        (r"\b(finan[ct]\w*|credit\w*|bancar\w*|tax\w*|buget\w*)\b", ("#Finante", "#Economie")),
        (r"\b(afacer\w*|investiti\w*|achiziti\w*|fuziun\w*|compani\w*)\b", ("#BusinessNews", "#Afaceri")),
        (r"\b(geopolitic\w*|diplomat\w*|nato|comert international)\b", ("#Geopolitica", "#WorldNews")),
        (r"\b(politic\w*|aleger\w*|parlament\w*|guvern\w*|presedint\w*)\b", ("#Politica", "#Actualitate")),
    ),
    "music": (
        (r"\b(latin grammys?|latin grammy awards)\b", ("#LatinGRAMMY", "#LatinMusic")),
        (r"\b(rosalia)\b", ("#Rosalia", "#LatinMusic")),
        (r"\b(duran duran)\b", ("#DuranDuran", "#NewWave", "#ClassicRock")),
        (r"\b(k[ -]?pop|2ne1)\b", ("#Kpop", "#KpopNews")),
        (r"\b(grammy|grammys)\b", ("#GRAMMYs", "#MusicNews")),
        (r"\b(hip[ -]?hop|rap|rapper\w*)\b", ("#HipHop", "#Rap")),
        (r"\b(rock|metal|punk)\b", ("#RockMusic", "#MusicNews")),
        (r"\b(spotify|streaming|casa de discuri|industrie muzicala)\b", ("#MusicIndustry", "#MusicBusiness")),
        (r"\b(concert\w*|turne\w*|festival\w*)\b", ("#LiveMusic", "#Concerte")),
        (r"\b(album\w*|single|lansar\w*)\b", ("#NewMusic", "#MusicNews")),
    ),
}


def hashtags_for(section: str, article: dict) -> list[str]:
    def fold(value):
        return unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii").lower()

    tags = {}
    overrides = article.get("hashtags")
    for tag in overrides if isinstance(overrides, list) else []:
        if isinstance(tag, str) and re.fullmatch(r"#[A-Za-z0-9_]{2,40}", tag) and not tag.lower().startswith("#acq"):
            tags.setdefault(tag.casefold(), tag)
    if tags:
        return list(tags.values())[:5]

    for searchable in (article.get("hed", ""), article.get("sum", ""), article.get("cat", "")):
        folded = fold(searchable)
        for pattern, matches in TOPIC_TAGS[section]:
            if re.search(pattern, folded):
                for tag in matches:
                    tags.setdefault(tag.casefold(), tag)
    return list(tags.values())[:5] or list(FALLBACK_TAGS[section])
