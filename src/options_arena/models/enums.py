"""Options Arena — StrEnum definitions for all domain enumerations.

All enums use Python 3.13+ ``enum.StrEnum`` with lowercase string values.
No business logic — pure data definitions only.
"""

from enum import StrEnum


class OptionType(StrEnum):
    """Type of option contract."""

    CALL = "call"
    PUT = "put"


class PositionSide(StrEnum):
    """Direction of a position (long or short)."""

    LONG = "long"
    SHORT = "short"


class SignalDirection(StrEnum):
    """Directional signal from indicators or analysis."""

    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


class ExerciseStyle(StrEnum):
    """Exercise style of an option contract.

    AMERICAN for all U.S. equity options; EUROPEAN for index options (SPX, etc.).
    Drives pricing dispatch: BAW for AMERICAN, BSM for EUROPEAN.
    """

    AMERICAN = "american"
    EUROPEAN = "european"


class PricingModel(StrEnum):
    """Pricing model used to compute Greeks.

    Tracked on every ``OptionGreeks`` instance so downstream consumers
    know which model produced the values.
    """

    BSM = "bsm"
    BAW = "baw"


class MarketCapTier(StrEnum):
    """Market capitalisation tier for ticker classification."""

    MEGA = "mega"
    LARGE = "large"
    MID = "mid"
    SMALL = "small"
    MICRO = "micro"


class DividendSource(StrEnum):
    """Provenance of the dividend yield value on ``TickerInfo``.

    Tracks which tier of the 3-tier waterfall produced the value:
      FORWARD  — yfinance ``info["dividendYield"]``
      TRAILING — yfinance ``info["trailingAnnualDividendYield"]``
      COMPUTED — ``sum(get_dividends("1y")) / price``
      NONE     — no dividend data available (yield defaults to 0.0)
    """

    FORWARD = "forward"
    TRAILING = "trailing"
    COMPUTED = "computed"
    NONE = "none"


class SpreadType(StrEnum):
    """Type of option spread strategy."""

    VERTICAL = "vertical"
    CALENDAR = "calendar"
    IRON_CONDOR = "iron_condor"
    STRADDLE = "straddle"
    STRANGLE = "strangle"
    BUTTERFLY = "butterfly"


class MacdSignal(StrEnum):
    """MACD crossover signal for market context.

    BULLISH_CROSSOVER — MACD line crossed above signal line.
    BEARISH_CROSSOVER — MACD line crossed below signal line.
    NEUTRAL           — no recent crossover.
    """

    BULLISH_CROSSOVER = "bullish_crossover"
    BEARISH_CROSSOVER = "bearish_crossover"
    NEUTRAL = "neutral"


class ScanPreset(StrEnum):
    """Scan universe preset for the scan pipeline.

    FULL  — full CBOE optionable universe.
    SP500 — S&P 500 constituents only.
    ETFS  — ETFs only.
    """

    FULL = "full"
    SP500 = "sp500"
    ETFS = "etfs"


class GreeksSource(StrEnum):
    """Source of Greeks values on an option contract.

    COMPUTED — locally computed via ``pricing/dispatch.py`` (BAW or BSM).
    MARKET   — sourced from market data provider (not used in MVP).
    """

    COMPUTED = "computed"
    MARKET = "market"


class VolAssessment(StrEnum):
    """Implied volatility assessment from the Volatility Agent.

    OVERPRICED  — IV is elevated, favors selling premium.
    UNDERPRICED — IV is depressed, favors buying premium.
    FAIR        — IV is fairly valued, no vol play warranted.
    """

    OVERPRICED = "overpriced"
    UNDERPRICED = "underpriced"
    FAIR = "fair"


class MarketRegime(StrEnum):
    """Market regime classification for regime-adjusted scoring weights."""

    TRENDING = "trending"
    MEAN_REVERTING = "mean_reverting"
    VOLATILE = "volatile"
    CRISIS = "crisis"


class VolRegime(StrEnum):
    """Implied volatility regime classification."""

    LOW = "low"
    NORMAL = "normal"
    ELEVATED = "elevated"
    EXTREME = "extreme"


class IVTermStructureShape(StrEnum):
    """IV term structure shape classification."""

    CONTANGO = "contango"
    FLAT = "flat"
    BACKWARDATION = "backwardation"


class RiskLevel(StrEnum):
    """Quantified risk level for risk assessment."""

    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    EXTREME = "extreme"


class CatalystImpact(StrEnum):
    """Expected impact of upcoming catalysts (earnings, dividends, etc.)."""

    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"


class SentimentLabel(StrEnum):
    """Sentiment classification for news or social media analysis.

    Used by OpenBB integration to label aggregate news sentiment.
    """

    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


class OutcomeCollectionMethod(StrEnum):
    """Method used to collect contract outcome data.

    MARKET          — market prices observed at exit date.
    INTRINSIC       — intrinsic value at expiration (max(S-K, 0) for calls).
    EXPIRED_WORTHLESS — contract expired out of the money (zero value).
    """

    MARKET = "market"
    INTRINSIC = "intrinsic"
    EXPIRED_WORTHLESS = "expired_worthless"


class GICSSector(StrEnum):
    """Global Industry Classification Standard (GICS) sectors.

    Exactly 11 sectors matching the canonical GICS taxonomy.
    Used for sector filtering in the scan pipeline.
    """

    COMMUNICATION_SERVICES = "Communication Services"
    CONSUMER_DISCRETIONARY = "Consumer Discretionary"
    CONSUMER_STAPLES = "Consumer Staples"
    ENERGY = "Energy"
    FINANCIALS = "Financials"
    HEALTH_CARE = "Health Care"
    INDUSTRIALS = "Industrials"
    INFORMATION_TECHNOLOGY = "Information Technology"
    MATERIALS = "Materials"
    REAL_ESTATE = "Real Estate"
    UTILITIES = "Utilities"


SECTOR_ALIASES: dict[str, GICSSector] = {
    # Canonical names (lowercase)
    "communication services": GICSSector.COMMUNICATION_SERVICES,
    "consumer discretionary": GICSSector.CONSUMER_DISCRETIONARY,
    "consumer staples": GICSSector.CONSUMER_STAPLES,
    "energy": GICSSector.ENERGY,
    "financials": GICSSector.FINANCIALS,
    "health care": GICSSector.HEALTH_CARE,
    "industrials": GICSSector.INDUSTRIALS,
    "information technology": GICSSector.INFORMATION_TECHNOLOGY,
    "materials": GICSSector.MATERIALS,
    "real estate": GICSSector.REAL_ESTATE,
    "utilities": GICSSector.UTILITIES,
    # Short names
    "communication": GICSSector.COMMUNICATION_SERVICES,
    "telecom": GICSSector.COMMUNICATION_SERVICES,
    "discretionary": GICSSector.CONSUMER_DISCRETIONARY,
    "staples": GICSSector.CONSUMER_STAPLES,
    "healthcare": GICSSector.HEALTH_CARE,
    "technology": GICSSector.INFORMATION_TECHNOLOGY,
    "tech": GICSSector.INFORMATION_TECHNOLOGY,
    "it": GICSSector.INFORMATION_TECHNOLOGY,
    # Hyphenated variants
    "communication-services": GICSSector.COMMUNICATION_SERVICES,
    "consumer-discretionary": GICSSector.CONSUMER_DISCRETIONARY,
    "consumer-staples": GICSSector.CONSUMER_STAPLES,
    "health-care": GICSSector.HEALTH_CARE,
    "information-technology": GICSSector.INFORMATION_TECHNOLOGY,
    "real-estate": GICSSector.REAL_ESTATE,
    # Underscored variants
    "communication_services": GICSSector.COMMUNICATION_SERVICES,
    "consumer_discretionary": GICSSector.CONSUMER_DISCRETIONARY,
    "consumer_staples": GICSSector.CONSUMER_STAPLES,
    "health_care": GICSSector.HEALTH_CARE,
    "information_technology": GICSSector.INFORMATION_TECHNOLOGY,
    "real_estate": GICSSector.REAL_ESTATE,
}


class GICSIndustryGroup(StrEnum):
    """GICS Industry Groups (2023 standard).

    Exactly 26 industry groups across 11 sectors. Each group maps to exactly
    one parent sector via ``SECTOR_TO_INDUSTRY_GROUPS``.
    """

    # Communication Services
    TELECOMMUNICATION_SERVICES = "Telecommunication Services"
    MEDIA_ENTERTAINMENT = "Media & Entertainment"
    # Consumer Discretionary
    AUTOMOBILES_COMPONENTS = "Automobiles & Components"
    CONSUMER_DURABLES_APPAREL = "Consumer Durables & Apparel"
    CONSUMER_SERVICES = "Consumer Services"
    RETAILING = "Retailing"
    # Consumer Staples
    FOOD_STAPLES_RETAILING = "Food & Staples Retailing"
    FOOD_BEVERAGE_TOBACCO = "Food Beverage & Tobacco"
    HOUSEHOLD_PERSONAL_PRODUCTS = "Household & Personal Products"
    # Energy
    ENERGY_EQUIPMENT_SERVICES = "Energy Equipment & Services"
    OIL_GAS_CONSUMABLE_FUELS = "Oil Gas & Consumable Fuels"
    # Financials
    BANKS = "Banks"
    DIVERSIFIED_FINANCIALS = "Diversified Financials"
    INSURANCE = "Insurance"
    # Health Care
    HEALTH_CARE_EQUIPMENT_SERVICES = "Health Care Equipment & Services"
    PHARMA_BIOTECH = "Pharmaceuticals Biotechnology & Life Sciences"
    # Industrials
    CAPITAL_GOODS = "Capital Goods"
    COMMERCIAL_PROFESSIONAL_SERVICES = "Commercial & Professional Services"
    TRANSPORTATION = "Transportation"
    # Information Technology
    SEMICONDUCTORS_EQUIPMENT = "Semiconductors & Semiconductor Equipment"
    SOFTWARE_SERVICES = "Software & Services"
    TECHNOLOGY_HARDWARE_EQUIPMENT = "Technology Hardware & Equipment"
    # Materials
    MATERIALS = "Materials"
    # Real Estate
    EQUITY_REITS = "Equity Real Estate Investment Trusts"
    REAL_ESTATE_MGMT_DEV = "Real Estate Management & Development"
    # Utilities
    UTILITIES = "Utilities"


INDUSTRY_GROUP_ALIASES: dict[str, GICSIndustryGroup] = {
    # --- Canonical lowercase ---
    "telecommunication services": GICSIndustryGroup.TELECOMMUNICATION_SERVICES,
    "media & entertainment": GICSIndustryGroup.MEDIA_ENTERTAINMENT,
    "automobiles & components": GICSIndustryGroup.AUTOMOBILES_COMPONENTS,
    "consumer durables & apparel": GICSIndustryGroup.CONSUMER_DURABLES_APPAREL,
    "consumer services": GICSIndustryGroup.CONSUMER_SERVICES,
    "retailing": GICSIndustryGroup.RETAILING,
    "food & staples retailing": GICSIndustryGroup.FOOD_STAPLES_RETAILING,
    "food beverage & tobacco": GICSIndustryGroup.FOOD_BEVERAGE_TOBACCO,
    "household & personal products": GICSIndustryGroup.HOUSEHOLD_PERSONAL_PRODUCTS,
    "energy equipment & services": GICSIndustryGroup.ENERGY_EQUIPMENT_SERVICES,
    "oil gas & consumable fuels": GICSIndustryGroup.OIL_GAS_CONSUMABLE_FUELS,
    "banks": GICSIndustryGroup.BANKS,
    "diversified financials": GICSIndustryGroup.DIVERSIFIED_FINANCIALS,
    "insurance": GICSIndustryGroup.INSURANCE,
    "health care equipment & services": GICSIndustryGroup.HEALTH_CARE_EQUIPMENT_SERVICES,
    "pharmaceuticals biotechnology & life sciences": GICSIndustryGroup.PHARMA_BIOTECH,
    "capital goods": GICSIndustryGroup.CAPITAL_GOODS,
    "commercial & professional services": GICSIndustryGroup.COMMERCIAL_PROFESSIONAL_SERVICES,
    "transportation": GICSIndustryGroup.TRANSPORTATION,
    "semiconductors & semiconductor equipment": GICSIndustryGroup.SEMICONDUCTORS_EQUIPMENT,
    "software & services": GICSIndustryGroup.SOFTWARE_SERVICES,
    "technology hardware & equipment": GICSIndustryGroup.TECHNOLOGY_HARDWARE_EQUIPMENT,
    "materials": GICSIndustryGroup.MATERIALS,
    "equity real estate investment trusts": GICSIndustryGroup.EQUITY_REITS,
    "real estate management & development": GICSIndustryGroup.REAL_ESTATE_MGMT_DEV,
    "utilities": GICSIndustryGroup.UTILITIES,
    # --- Short names ---
    "telecom": GICSIndustryGroup.TELECOMMUNICATION_SERVICES,
    "telco": GICSIndustryGroup.TELECOMMUNICATION_SERVICES,
    "media": GICSIndustryGroup.MEDIA_ENTERTAINMENT,
    "entertainment": GICSIndustryGroup.MEDIA_ENTERTAINMENT,
    "autos": GICSIndustryGroup.AUTOMOBILES_COMPONENTS,
    "automobiles": GICSIndustryGroup.AUTOMOBILES_COMPONENTS,
    "durables": GICSIndustryGroup.CONSUMER_DURABLES_APPAREL,
    "apparel": GICSIndustryGroup.CONSUMER_DURABLES_APPAREL,
    "retail": GICSIndustryGroup.RETAILING,
    "food retail": GICSIndustryGroup.FOOD_STAPLES_RETAILING,
    "food": GICSIndustryGroup.FOOD_BEVERAGE_TOBACCO,
    "beverage": GICSIndustryGroup.FOOD_BEVERAGE_TOBACCO,
    "tobacco": GICSIndustryGroup.FOOD_BEVERAGE_TOBACCO,
    "household": GICSIndustryGroup.HOUSEHOLD_PERSONAL_PRODUCTS,
    "personal products": GICSIndustryGroup.HOUSEHOLD_PERSONAL_PRODUCTS,
    "energy equipment": GICSIndustryGroup.ENERGY_EQUIPMENT_SERVICES,
    "oil gas": GICSIndustryGroup.OIL_GAS_CONSUMABLE_FUELS,
    "oil & gas": GICSIndustryGroup.OIL_GAS_CONSUMABLE_FUELS,
    "diversified finance": GICSIndustryGroup.DIVERSIFIED_FINANCIALS,
    "health care equipment": GICSIndustryGroup.HEALTH_CARE_EQUIPMENT_SERVICES,
    "pharma": GICSIndustryGroup.PHARMA_BIOTECH,
    "biotech": GICSIndustryGroup.PHARMA_BIOTECH,
    "pharmaceuticals": GICSIndustryGroup.PHARMA_BIOTECH,
    "semiconductors": GICSIndustryGroup.SEMICONDUCTORS_EQUIPMENT,
    "semis": GICSIndustryGroup.SEMICONDUCTORS_EQUIPMENT,
    "software": GICSIndustryGroup.SOFTWARE_SERVICES,
    "hardware": GICSIndustryGroup.TECHNOLOGY_HARDWARE_EQUIPMENT,
    "tech hardware": GICSIndustryGroup.TECHNOLOGY_HARDWARE_EQUIPMENT,
    "reits": GICSIndustryGroup.EQUITY_REITS,
    "real estate mgmt": GICSIndustryGroup.REAL_ESTATE_MGMT_DEV,
    # --- Hyphenated variants ---
    "telecommunication-services": GICSIndustryGroup.TELECOMMUNICATION_SERVICES,
    "media-entertainment": GICSIndustryGroup.MEDIA_ENTERTAINMENT,
    "automobiles-components": GICSIndustryGroup.AUTOMOBILES_COMPONENTS,
    "consumer-durables-apparel": GICSIndustryGroup.CONSUMER_DURABLES_APPAREL,
    "consumer-services": GICSIndustryGroup.CONSUMER_SERVICES,
    "food-staples-retailing": GICSIndustryGroup.FOOD_STAPLES_RETAILING,
    "food-beverage-tobacco": GICSIndustryGroup.FOOD_BEVERAGE_TOBACCO,
    "household-personal-products": GICSIndustryGroup.HOUSEHOLD_PERSONAL_PRODUCTS,
    "energy-equipment-services": GICSIndustryGroup.ENERGY_EQUIPMENT_SERVICES,
    "oil-gas-consumable-fuels": GICSIndustryGroup.OIL_GAS_CONSUMABLE_FUELS,
    "diversified-financials": GICSIndustryGroup.DIVERSIFIED_FINANCIALS,
    "health-care-equipment-services": GICSIndustryGroup.HEALTH_CARE_EQUIPMENT_SERVICES,
    "pharma-biotech": GICSIndustryGroup.PHARMA_BIOTECH,
    "capital-goods": GICSIndustryGroup.CAPITAL_GOODS,
    "commercial-professional-services": GICSIndustryGroup.COMMERCIAL_PROFESSIONAL_SERVICES,
    "semiconductors-equipment": GICSIndustryGroup.SEMICONDUCTORS_EQUIPMENT,
    "software-services": GICSIndustryGroup.SOFTWARE_SERVICES,
    "technology-hardware-equipment": GICSIndustryGroup.TECHNOLOGY_HARDWARE_EQUIPMENT,
    "equity-reits": GICSIndustryGroup.EQUITY_REITS,
    "real-estate-mgmt-dev": GICSIndustryGroup.REAL_ESTATE_MGMT_DEV,
    # --- Underscored variants ---
    "telecommunication_services": GICSIndustryGroup.TELECOMMUNICATION_SERVICES,
    "media_entertainment": GICSIndustryGroup.MEDIA_ENTERTAINMENT,
    "automobiles_components": GICSIndustryGroup.AUTOMOBILES_COMPONENTS,
    "consumer_durables_apparel": GICSIndustryGroup.CONSUMER_DURABLES_APPAREL,
    "consumer_services": GICSIndustryGroup.CONSUMER_SERVICES,
    "food_staples_retailing": GICSIndustryGroup.FOOD_STAPLES_RETAILING,
    "food_beverage_tobacco": GICSIndustryGroup.FOOD_BEVERAGE_TOBACCO,
    "household_personal_products": GICSIndustryGroup.HOUSEHOLD_PERSONAL_PRODUCTS,
    "energy_equipment_services": GICSIndustryGroup.ENERGY_EQUIPMENT_SERVICES,
    "oil_gas_consumable_fuels": GICSIndustryGroup.OIL_GAS_CONSUMABLE_FUELS,
    "diversified_financials": GICSIndustryGroup.DIVERSIFIED_FINANCIALS,
    "health_care_equipment_services": GICSIndustryGroup.HEALTH_CARE_EQUIPMENT_SERVICES,
    "pharma_biotech": GICSIndustryGroup.PHARMA_BIOTECH,
    "capital_goods": GICSIndustryGroup.CAPITAL_GOODS,
    "commercial_professional_services": GICSIndustryGroup.COMMERCIAL_PROFESSIONAL_SERVICES,
    "semiconductors_equipment": GICSIndustryGroup.SEMICONDUCTORS_EQUIPMENT,
    "software_services": GICSIndustryGroup.SOFTWARE_SERVICES,
    "technology_hardware_equipment": GICSIndustryGroup.TECHNOLOGY_HARDWARE_EQUIPMENT,
    "equity_reits": GICSIndustryGroup.EQUITY_REITS,
    "real_estate_mgmt_dev": GICSIndustryGroup.REAL_ESTATE_MGMT_DEV,
    # --- yfinance industry field mappings ---
    # NOTE: "semiconductors" already in short names section above
    "software—application": GICSIndustryGroup.SOFTWARE_SERVICES,
    "software—infrastructure": GICSIndustryGroup.SOFTWARE_SERVICES,
    "software - application": GICSIndustryGroup.SOFTWARE_SERVICES,
    "software - infrastructure": GICSIndustryGroup.SOFTWARE_SERVICES,
    "internet retail": GICSIndustryGroup.RETAILING,
    "internet content & information": GICSIndustryGroup.MEDIA_ENTERTAINMENT,
    "biotechnology": GICSIndustryGroup.PHARMA_BIOTECH,
    "drug manufacturers—general": GICSIndustryGroup.PHARMA_BIOTECH,
    "drug manufacturers - general": GICSIndustryGroup.PHARMA_BIOTECH,
    "drug manufacturers—specialty & generic": GICSIndustryGroup.PHARMA_BIOTECH,
    "drug manufacturers - specialty & generic": GICSIndustryGroup.PHARMA_BIOTECH,
    "auto manufacturers": GICSIndustryGroup.AUTOMOBILES_COMPONENTS,
    "auto parts": GICSIndustryGroup.AUTOMOBILES_COMPONENTS,
    "aerospace & defense": GICSIndustryGroup.CAPITAL_GOODS,
    "building products & equipment": GICSIndustryGroup.CAPITAL_GOODS,
    "specialty industrial machinery": GICSIndustryGroup.CAPITAL_GOODS,
    "electrical equipment & parts": GICSIndustryGroup.CAPITAL_GOODS,
    "farm & heavy construction machinery": GICSIndustryGroup.CAPITAL_GOODS,
    "railroads": GICSIndustryGroup.TRANSPORTATION,
    "airlines": GICSIndustryGroup.TRANSPORTATION,
    "trucking": GICSIndustryGroup.TRANSPORTATION,
    "integrated freight & logistics": GICSIndustryGroup.TRANSPORTATION,
    "banks—diversified": GICSIndustryGroup.BANKS,
    "banks - diversified": GICSIndustryGroup.BANKS,
    "banks—regional": GICSIndustryGroup.BANKS,
    "banks - regional": GICSIndustryGroup.BANKS,
    "insurance—diversified": GICSIndustryGroup.INSURANCE,
    "insurance - diversified": GICSIndustryGroup.INSURANCE,
    "insurance—life": GICSIndustryGroup.INSURANCE,
    "insurance - life": GICSIndustryGroup.INSURANCE,
    "insurance—property & casualty": GICSIndustryGroup.INSURANCE,
    "insurance - property & casualty": GICSIndustryGroup.INSURANCE,
    "credit services": GICSIndustryGroup.DIVERSIFIED_FINANCIALS,
    "capital markets": GICSIndustryGroup.DIVERSIFIED_FINANCIALS,
    "financial data & stock exchanges": GICSIndustryGroup.DIVERSIFIED_FINANCIALS,
    "asset management": GICSIndustryGroup.DIVERSIFIED_FINANCIALS,
    "medical devices": GICSIndustryGroup.HEALTH_CARE_EQUIPMENT_SERVICES,
    "health information services": GICSIndustryGroup.HEALTH_CARE_EQUIPMENT_SERVICES,
    "medical instruments & supplies": GICSIndustryGroup.HEALTH_CARE_EQUIPMENT_SERVICES,
    "diagnostics & research": GICSIndustryGroup.HEALTH_CARE_EQUIPMENT_SERVICES,
    # NOTE: "household & personal products" already in canonical section above
    "packaged foods": GICSIndustryGroup.FOOD_BEVERAGE_TOBACCO,
    "beverages—non-alcoholic": GICSIndustryGroup.FOOD_BEVERAGE_TOBACCO,
    "beverages - non-alcoholic": GICSIndustryGroup.FOOD_BEVERAGE_TOBACCO,
    "discount stores": GICSIndustryGroup.RETAILING,
    "specialty retail": GICSIndustryGroup.RETAILING,
    "home improvement retail": GICSIndustryGroup.RETAILING,
    "apparel retail": GICSIndustryGroup.RETAILING,
    "restaurants": GICSIndustryGroup.CONSUMER_SERVICES,
    "resorts & casinos": GICSIndustryGroup.CONSUMER_SERVICES,
    "lodging": GICSIndustryGroup.CONSUMER_SERVICES,
    # NOTE: "entertainment" already in short names section above
    "electronic gaming & multimedia": GICSIndustryGroup.MEDIA_ENTERTAINMENT,
    "advertising agencies": GICSIndustryGroup.MEDIA_ENTERTAINMENT,
    "communication equipment": GICSIndustryGroup.TECHNOLOGY_HARDWARE_EQUIPMENT,
    "consumer electronics": GICSIndustryGroup.TECHNOLOGY_HARDWARE_EQUIPMENT,
    "scientific & technical instruments": GICSIndustryGroup.TECHNOLOGY_HARDWARE_EQUIPMENT,
    "information technology services": GICSIndustryGroup.SOFTWARE_SERVICES,
    "semiconductor equipment & materials": GICSIndustryGroup.SEMICONDUCTORS_EQUIPMENT,
    "oil & gas integrated": GICSIndustryGroup.OIL_GAS_CONSUMABLE_FUELS,
    "oil & gas e&p": GICSIndustryGroup.OIL_GAS_CONSUMABLE_FUELS,
    "oil & gas midstream": GICSIndustryGroup.OIL_GAS_CONSUMABLE_FUELS,
    "oil & gas equipment & services": GICSIndustryGroup.ENERGY_EQUIPMENT_SERVICES,
    "utilities—regulated electric": GICSIndustryGroup.UTILITIES,
    "utilities - regulated electric": GICSIndustryGroup.UTILITIES,
    "utilities—diversified": GICSIndustryGroup.UTILITIES,
    "utilities - diversified": GICSIndustryGroup.UTILITIES,
    "utilities—renewable": GICSIndustryGroup.UTILITIES,
    "utilities - renewable": GICSIndustryGroup.UTILITIES,
    "reit—residential": GICSIndustryGroup.EQUITY_REITS,
    "reit - residential": GICSIndustryGroup.EQUITY_REITS,
    "reit—industrial": GICSIndustryGroup.EQUITY_REITS,
    "reit - industrial": GICSIndustryGroup.EQUITY_REITS,
    "reit—retail": GICSIndustryGroup.EQUITY_REITS,
    "reit - retail": GICSIndustryGroup.EQUITY_REITS,
    "real estate services": GICSIndustryGroup.REAL_ESTATE_MGMT_DEV,
    "real estate—development": GICSIndustryGroup.REAL_ESTATE_MGMT_DEV,
    "real estate - development": GICSIndustryGroup.REAL_ESTATE_MGMT_DEV,
    "gold": GICSIndustryGroup.MATERIALS,
    "copper": GICSIndustryGroup.MATERIALS,
    "steel": GICSIndustryGroup.MATERIALS,
    "specialty chemicals": GICSIndustryGroup.MATERIALS,
    "agricultural inputs": GICSIndustryGroup.MATERIALS,
    "staffing & employment services": GICSIndustryGroup.COMMERCIAL_PROFESSIONAL_SERVICES,
    "consulting services": GICSIndustryGroup.COMMERCIAL_PROFESSIONAL_SERVICES,
    "waste management": GICSIndustryGroup.COMMERCIAL_PROFESSIONAL_SERVICES,
    "security & protection services": GICSIndustryGroup.COMMERCIAL_PROFESSIONAL_SERVICES,
    "grocery stores": GICSIndustryGroup.FOOD_STAPLES_RETAILING,
    "food distribution": GICSIndustryGroup.FOOD_STAPLES_RETAILING,
    "telecom services": GICSIndustryGroup.TELECOMMUNICATION_SERVICES,
}


SECTOR_TO_INDUSTRY_GROUPS: dict[GICSSector, list[GICSIndustryGroup]] = {
    GICSSector.COMMUNICATION_SERVICES: [
        GICSIndustryGroup.TELECOMMUNICATION_SERVICES,
        GICSIndustryGroup.MEDIA_ENTERTAINMENT,
    ],
    GICSSector.CONSUMER_DISCRETIONARY: [
        GICSIndustryGroup.AUTOMOBILES_COMPONENTS,
        GICSIndustryGroup.CONSUMER_DURABLES_APPAREL,
        GICSIndustryGroup.CONSUMER_SERVICES,
        GICSIndustryGroup.RETAILING,
    ],
    GICSSector.CONSUMER_STAPLES: [
        GICSIndustryGroup.FOOD_STAPLES_RETAILING,
        GICSIndustryGroup.FOOD_BEVERAGE_TOBACCO,
        GICSIndustryGroup.HOUSEHOLD_PERSONAL_PRODUCTS,
    ],
    GICSSector.ENERGY: [
        GICSIndustryGroup.ENERGY_EQUIPMENT_SERVICES,
        GICSIndustryGroup.OIL_GAS_CONSUMABLE_FUELS,
    ],
    GICSSector.FINANCIALS: [
        GICSIndustryGroup.BANKS,
        GICSIndustryGroup.DIVERSIFIED_FINANCIALS,
        GICSIndustryGroup.INSURANCE,
    ],
    GICSSector.HEALTH_CARE: [
        GICSIndustryGroup.HEALTH_CARE_EQUIPMENT_SERVICES,
        GICSIndustryGroup.PHARMA_BIOTECH,
    ],
    GICSSector.INDUSTRIALS: [
        GICSIndustryGroup.CAPITAL_GOODS,
        GICSIndustryGroup.COMMERCIAL_PROFESSIONAL_SERVICES,
        GICSIndustryGroup.TRANSPORTATION,
    ],
    GICSSector.INFORMATION_TECHNOLOGY: [
        GICSIndustryGroup.SEMICONDUCTORS_EQUIPMENT,
        GICSIndustryGroup.SOFTWARE_SERVICES,
        GICSIndustryGroup.TECHNOLOGY_HARDWARE_EQUIPMENT,
    ],
    GICSSector.MATERIALS: [
        GICSIndustryGroup.MATERIALS,
    ],
    GICSSector.REAL_ESTATE: [
        GICSIndustryGroup.EQUITY_REITS,
        GICSIndustryGroup.REAL_ESTATE_MGMT_DEV,
    ],
    GICSSector.UTILITIES: [
        GICSIndustryGroup.UTILITIES,
    ],
}
