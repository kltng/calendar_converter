"""
Add Vietnamese calendar data to the SQLite database.

Vietnamese calendar eras derived from historical records. Since DILA only covers
Chinese, Japanese, and Korean calendars, this script adds Vietnamese dynasties
and eras.

The Vietnamese calendar was essentially the Chinese lunisolar calendar with local
era names, so we reuse Chinese lunar month data (JDN ranges) for the overlapping
periods and link Vietnamese eras to them.

Usage:
    uv run python -m data.scripts.add_vietnamese
"""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "calendar.db"

# Vietnamese dynasties and their eras
# Format: (dynasty_name, [(emperor_name, era_name, start_year_ce, end_year_ce), ...])
# Source: Vietnamese historical records, Đại Việt sử ký toàn thư
VIETNAMESE_DATA: list[tuple[str, list[tuple[str, str, int, int]]]] = [
    ("前李朝", [
        ("李南帝", "天德", 544, 548),
    ]),
    ("吳朝", [
        ("吳權", "吳王", 939, 944),
        ("楊三哥", "楊主", 945, 950),
        ("吳昌岌", "天策", 951, 954),
        ("吳昌文", "吳使君", 955, 965),
    ]),
    ("丁朝", [
        ("丁先皇", "太平", 970, 979),
    ]),
    ("前黎朝", [
        ("黎大行", "天福", 980, 988),
        ("黎大行", "興統", 989, 993),
        ("黎大行", "應天", 994, 1005),
        ("黎中宗", "景瑞", 1008, 1009),
    ]),
    ("李朝", [
        ("李太祖", "順天", 1010, 1028),
        ("李太宗", "天成", 1028, 1034),
        ("李太宗", "通瑞", 1034, 1039),
        ("李太宗", "乾符有道", 1039, 1042),
        ("李太宗", "明道", 1042, 1044),
        ("李太宗", "天感聖武", 1044, 1049),
        ("李太宗", "崇興大寶", 1049, 1054),
        ("李聖宗", "龍瑞太平", 1054, 1058),
        ("李聖宗", "彰聖嘉慶", 1059, 1065),
        ("李聖宗", "龍彰天嗣", 1066, 1068),
        ("李聖宗", "天貺寶象", 1068, 1069),
        ("李聖宗", "神武", 1069, 1072),
        ("李仁宗", "太寧", 1072, 1076),
        ("李仁宗", "英武昭勝", 1076, 1084),
        ("李仁宗", "廣祐", 1085, 1092),
        ("李仁宗", "會豐", 1092, 1100),
        ("李仁宗", "龍符", 1101, 1109),
        ("李仁宗", "會祥大慶", 1110, 1119),
        ("李仁宗", "天符睿武", 1120, 1126),
        ("李仁宗", "天符慶壽", 1127, 1127),
        ("李神宗", "天順", 1128, 1132),
        ("李神宗", "天彰寶嗣", 1133, 1138),
        ("李英宗", "紹明", 1138, 1140),
        ("李英宗", "大定", 1140, 1162),
        ("李英宗", "政隆寶應", 1163, 1174),
        ("李英宗", "天感至寶", 1174, 1175),
        ("李高宗", "貞符", 1176, 1186),
        ("李高宗", "天資嘉瑞", 1186, 1202),
        ("李高宗", "天嘉寶祐", 1202, 1205),
        ("李高宗", "治平龍應", 1205, 1210),
        ("李惠宗", "建嘉", 1211, 1224),
        ("李昭皇", "天彰有道", 1224, 1225),
    ]),
    ("陳朝", [
        ("陳太宗", "建中", 1225, 1232),
        ("陳太宗", "天應政平", 1232, 1251),
        ("陳聖宗", "元豐", 1251, 1258),
        ("陳聖宗", "紹隆", 1258, 1273),
        ("陳聖宗", "寶符", 1273, 1278),
        ("陳仁宗", "紹寶", 1279, 1285),
        ("陳仁宗", "重興", 1285, 1293),
        ("陳英宗", "興隆", 1293, 1314),
        ("陳明宗", "大慶", 1314, 1324),
        ("陳明宗", "開泰", 1324, 1329),
        ("陳憲宗", "開祐", 1329, 1341),
        ("陳裕宗", "紹豐", 1341, 1357),
        ("陳裕宗", "大治", 1358, 1369),
        ("陳藝宗", "大定", 1369, 1370),
        ("陳睿宗", "隆慶", 1373, 1377),
        ("陳廢帝", "昌符", 1377, 1388),
        ("陳順宗", "光泰", 1388, 1398),
        ("陳少帝", "建新", 1398, 1400),
    ]),
    ("胡朝", [
        ("胡季犛", "聖元", 1400, 1401),
        ("胡漢蒼", "紹成", 1401, 1403),
        ("胡漢蒼", "開大", 1403, 1407),
    ]),
    ("後陳朝", [
        ("簡定帝", "興慶", 1407, 1409),
        ("重光帝", "重光", 1409, 1414),
    ]),
    ("後黎朝", [
        ("黎太祖", "順天", 1428, 1433),
        ("黎太宗", "紹平", 1434, 1439),
        ("黎太宗", "大寶", 1440, 1442),
        ("黎仁宗", "大和", 1443, 1453),
        ("黎仁宗", "延寧", 1454, 1459),
        ("黎聖宗", "光順", 1460, 1469),
        ("黎聖宗", "洪德", 1470, 1497),
        ("黎憲宗", "景統", 1498, 1504),
        ("黎肅宗", "泰貞", 1504, 1504),
        ("黎威穆帝", "端慶", 1505, 1509),
        ("黎襄翼帝", "洪順", 1509, 1516),
        ("黎昭宗", "光紹", 1516, 1522),
        ("黎恭皇", "統元", 1522, 1527),
        ("黎莊宗", "元和", 1533, 1548),
        ("黎中宗", "順平", 1549, 1556),
        ("黎英宗", "天祐", 1557, 1572),
        ("黎世宗", "嘉泰", 1573, 1577),
        ("黎世宗", "光興", 1578, 1599),
        ("黎敬宗", "慎德", 1600, 1601),
        ("黎敬宗", "弘定", 1601, 1619),
        ("黎神宗", "永祚", 1619, 1629),
        ("黎神宗", "德隆", 1629, 1635),
        ("黎神宗", "陽和", 1635, 1643),
        ("黎真宗", "福泰", 1643, 1649),
        ("黎神宗", "慶德", 1649, 1652),
        ("黎神宗", "盛德", 1653, 1657),
        ("黎神宗", "永壽", 1658, 1662),
        ("黎玄宗", "景治", 1663, 1671),
        ("黎嘉宗", "陽德", 1672, 1674),
        ("黎熙宗", "德元", 1674, 1675),
        ("黎熙宗", "永治", 1676, 1680),
        ("黎熙宗", "正和", 1680, 1705),
        ("黎裕宗", "永盛", 1705, 1720),
        ("黎裕宗", "保泰", 1720, 1729),
        ("黎昏德公", "永慶", 1729, 1732),
        ("黎純宗", "龍德", 1732, 1735),
        ("黎懿宗", "永佑", 1735, 1740),
        ("黎顯宗", "景興", 1740, 1786),
        ("黎愍帝", "昭統", 1787, 1789),
    ]),
    ("莫朝", [
        ("莫太祖", "明德", 1527, 1530),
        ("莫太宗", "大正", 1530, 1540),
        ("莫太宗", "廣和", 1540, 1546),
        ("莫憲宗", "永定", 1547, 1548),
        ("莫憲宗", "景歷", 1548, 1553),
        ("莫宣宗", "光寶", 1554, 1561),
        ("莫茂洽", "淳福", 1562, 1566),
        ("莫茂洽", "崇康", 1566, 1578),
        ("莫茂洽", "延成", 1578, 1585),
        ("莫茂洽", "端泰", 1586, 1587),
        ("莫茂洽", "興治", 1588, 1590),
        ("莫全", "武安", 1592, 1592),
        ("莫敬止", "寶定", 1592, 1593),
        ("莫敬恭", "乾統", 1593, 1625),
    ]),
    ("西山朝", [
        ("阮岳", "泰德", 1778, 1793),
        ("阮光纘", "景盛", 1793, 1801),
        ("阮光纘", "寶興", 1801, 1802),
    ]),
    ("阮朝", [
        ("阮世祖", "嘉隆", 1802, 1820),
        ("阮聖祖", "明命", 1820, 1841),
        ("阮憲祖", "紹治", 1841, 1847),
        ("阮翼宗", "嗣德", 1848, 1883),
        ("阮恭宗", "育德", 1883, 1883),
        ("阮簡宗", "協和", 1883, 1883),
        ("阮簡宗", "建福", 1884, 1885),
        ("阮景宗", "咸宜", 1885, 1888),
        ("阮景宗", "同慶", 1886, 1888),
        ("阮成泰帝", "成泰", 1889, 1907),
        ("阮維新帝", "維新", 1907, 1916),
        ("阮弘宗", "啟定", 1916, 1925),
        ("阮保大帝", "保大", 1926, 1945),
    ]),
]


def add_vietnamese_data() -> None:
    """Add Vietnamese dynasty/emperor/era data to the database."""
    if not DB_PATH.exists():
        print("ERROR: Database not found. Run build_db first.")
        return

    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA foreign_keys=ON")

    # Check if Vietnamese data already exists
    existing = conn.execute(
        "SELECT COUNT(*) FROM dynasty WHERE type = 'vietnamese'"
    ).fetchone()[0]
    if existing > 0:
        print("Vietnamese data already exists. Skipping.")
        conn.close()
        return

    # We need to find the next available IDs
    max_dynasty_id = conn.execute("SELECT COALESCE(MAX(id), 0) FROM dynasty").fetchone()[0]
    max_emperor_id = conn.execute("SELECT COALESCE(MAX(id), 0) FROM emperor").fetchone()[0]
    max_era_id = conn.execute("SELECT COALESCE(MAX(id), 0) FROM era").fetchone()[0]

    dynasty_id = max_dynasty_id + 1
    emperor_id = max_emperor_id + 1
    era_id = max_era_id + 1

    # Get Chinese month data for date mapping
    # We'll link Vietnamese eras to Chinese months via JDN ranges
    # First, build a mapping of Gregorian year → approximate JDN for Jan 1
    def approx_jdn_for_year(year: int) -> int:
        """Approximate JDN for start of a Chinese lunar year."""
        # Use Chinese month data: find the first month of the closest Chinese year
        row = conn.execute("""
            SELECT MIN(first_jdn) FROM month m
            JOIN era e ON e.id = m.era_id
            JOIN emperor emp ON emp.id = e.emperor_id
            JOIN dynasty d ON d.id = emp.dynasty_id
            WHERE d.type = 'chinese'
            AND m.first_jdn BETWEEN ? AND ?
            AND m.month = 1 AND m.leap_month = 0
        """, (
            # Approximate JDN: year * 365.25 + offset
            int(year * 365.25 + 1721424.5 - 30),
            int(year * 365.25 + 1721424.5 + 60),
        )).fetchone()[0]
        if row:
            return row
        # Fallback: compute from Gregorian
        a = (14 - 1) // 12
        y = year + 4800 - a
        m = 1 + 12 * a - 3
        return 1 + (153 * m + 2) // 5 + 365 * y + y // 4 - y // 100 + y // 400 - 32045

    total_eras = 0
    total_months = 0

    for dynasty_name, emperors_data in VIETNAMESE_DATA:
        # Insert dynasty
        conn.execute("INSERT INTO dynasty (id, type) VALUES (?, 'vietnamese')", (dynasty_id,))
        conn.execute(
            "INSERT INTO dynasty_name (dynasty_id, name, ranking, language_id) VALUES (?, ?, 0, 1)",
            (dynasty_id, dynasty_name),
        )

        # Group by emperor name
        seen_emperors: dict[str, int] = {}

        for emperor_name, era_name, start_year, end_year in emperors_data:
            if emperor_name not in seen_emperors:
                conn.execute(
                    "INSERT INTO emperor (id, dynasty_id) VALUES (?, ?)",
                    (emperor_id, dynasty_id),
                )
                conn.execute(
                    "INSERT INTO emperor_name (emperor_id, name, ranking, language_id) VALUES (?, ?, 0, 1)",
                    (emperor_id, emperor_name),
                )
                seen_emperors[emperor_name] = emperor_id
                emperor_id += 1

            emp_id = seen_emperors[emperor_name]

            # Insert era
            conn.execute(
                "INSERT INTO era (id, emperor_id) VALUES (?, ?)",
                (era_id, emp_id),
            )
            conn.execute(
                "INSERT INTO era_name (era_id, name, ranking, language_id) VALUES (?, ?, 0, 1)",
                (era_id, era_name),
            )

            # Link to Chinese lunar months for the same period
            # Vietnamese used the same lunisolar calendar as China
            start_jdn = approx_jdn_for_year(start_year)
            end_jdn = approx_jdn_for_year(end_year + 1)

            # Find Chinese months in this range and create Vietnamese month records
            # Use DISTINCT on first_jdn to avoid duplicates from overlapping eras
            chinese_months = conn.execute("""
                SELECT m.month, m.month_name, m.leap_month, m.first_jdn, m.last_jdn,
                       m.ganzhi, m.start_from, m.eclipse
                FROM month m
                JOIN era e ON e.id = m.era_id
                JOIN emperor emp ON emp.id = e.emperor_id
                JOIN dynasty d ON d.id = emp.dynasty_id
                WHERE d.type = 'chinese'
                AND m.first_jdn >= ? AND m.first_jdn <= ?
                AND m.status = 'S'
                GROUP BY m.first_jdn
                ORDER BY m.first_jdn
            """, (start_jdn, end_jdn)).fetchall()

            # Get next month ID
            max_month_id = conn.execute("SELECT COALESCE(MAX(id), 0) FROM month").fetchone()[0]
            month_id = max_month_id + 1

            # Track era year: detect boundaries when month number resets
            current_year = 1
            last_month = 0

            for cm in chinese_months:
                month_num = cm[0]
                is_leap = cm[2]
                # Year boundary: when month number wraps (e.g., 12→1)
                # Leap months don't trigger year change
                if month_num <= last_month and last_month > 0 and not is_leap:
                    current_year += 1
                if not is_leap:
                    last_month = month_num

                conn.execute("""
                    INSERT INTO month (id, year, month, month_name, leap_month,
                                       era_id, first_jdn, last_jdn, ganzhi,
                                       start_from, status, eclipse)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'S', ?)
                """, (
                    month_id, current_year, month_num, cm[1], cm[2],
                    era_id, cm[3], cm[4], cm[5], cm[6], cm[7],
                ))
                month_id += 1
                total_months += 1

            era_id += 1
            total_eras += 1

        dynasty_id += 1

    # Recreate the era_summary view to include Vietnamese
    conn.execute("DROP VIEW IF EXISTS era_summary")
    conn.execute("""
        CREATE VIEW era_summary AS
        SELECT
            e.id AS era_id,
            en.name AS era_name,
            emp.id AS emperor_id,
            empn.name AS emperor_name,
            d.id AS dynasty_id,
            dn.name AS dynasty_name,
            d.type AS country,
            MIN(m.first_jdn) AS start_jdn,
            MAX(m.last_jdn) AS end_jdn
        FROM era e
        JOIN era_name en ON en.era_id = e.id AND en.ranking = 0
        JOIN emperor emp ON emp.id = e.emperor_id
        LEFT JOIN emperor_name empn ON empn.emperor_id = emp.id AND empn.ranking = 0
        JOIN dynasty d ON d.id = emp.dynasty_id
        LEFT JOIN dynasty_name dn ON dn.dynasty_id = d.id AND dn.ranking = 0
        LEFT JOIN month m ON m.era_id = e.id
        GROUP BY e.id
    """)

    conn.commit()

    # Stats
    vn_eras = conn.execute(
        "SELECT COUNT(*) FROM era_summary WHERE country = 'vietnamese'"
    ).fetchone()[0]
    print(f"Added Vietnamese data:")
    print(f"  Dynasties: {len(VIETNAMESE_DATA)}")
    print(f"  Eras: {total_eras}")
    print(f"  Month records: {total_months}")
    print(f"  Eras in view: {vn_eras}")

    conn.close()


if __name__ == "__main__":
    add_vietnamese_data()
