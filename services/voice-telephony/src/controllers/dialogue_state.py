class DialogueState:
    def __init__(self):
        self.context = {}

    def update(self, key: str, value: str):
        self.context[key] = value


class ArabicDialogueController:
    """Simple Arabic dialogue controller for local member-1 testing."""

    def __init__(self):
        self.state = "IDLE"
        self.context = {}

    def get_initial_greeting(self) -> str:
        return "مرحبا، كيف أستطيع مساعدتك اليوم؟"

    def process_turn(self, customer_text: str):
        text = (customer_text or "").strip()
        lowered = text.lower()

        if any(keyword in lowered for keyword in ["نعم", "تم", "حل", "مشكلة"]):
            return "تم حل مشكلتك بنجاح. شكراً لاستخدامنا.", "RESOLVED", False

        if any(keyword in lowered for keyword in ["لا", "غير", "مستعصي", "محتاج", "انسان"]):
            return "سأحولك إلى فريق الدعم البشري الآن.", "NEEDS_HUMAN", True

        return "أفهم طلبك. سأواصل مساعدتك.", "IN_PROGRESS", False

    def update(self, key: str, value: str):
        self.context[key] = value

    def reset(self):
        self.context = {}
        self.state = "IDLE"
