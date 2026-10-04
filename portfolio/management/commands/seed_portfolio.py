from django.core.management.base import BaseCommand

from portfolio.models import Category, SiteSettings


CATEGORIES = [
    ("race-day", "Race day", "Jour de course"),
    ("endurance", "Endurance", "Endurance"),
    ("team-sports", "Team sports", "Sports d'\u00e9quipe"),
    ("athlete-stories", "Athlete stories", "Histoires d'athl\u00e8tes"),
]


class Command(BaseCommand):
    help = "Create the starting site content without overwriting owner edits."

    def handle(self, *args, **options):
        SiteSettings.objects.get_or_create(singleton=1, defaults={
            "instagram_url": "https://www.instagram.com/mrsaintj/",
            "linkedin_url": "https://www.linkedin.com/in/mrsaintj123/",
            "biography_en": "I'm Justin St-Laurent, the photographer behind MrSaintJ Photography. Based on Montr\u00e9al's South Shore, I photograph sport and the people who give it meaning.",
            "biography_fr": "Je suis Justin St-Laurent, le photographe derri\u00e8re MrSaintJ Photography. Bas\u00e9 sur la Rive-Sud de Montr\u00e9al, je photographie le sport et les gens qui lui donnent son sens.",
            "approach_en": "My goal is to hold onto the moments that matter: the commitment before an obstacle, the split second at the net, the relief when the effort is over.\n\nI follow the action and stay attentive to everything around it. Determination, connection, and celebration are all part of the same story.",
            "approach_fr": "Mon objectif : saisir les moments qui comptent. L'engagement devant un obstacle, la fraction de seconde au filet, le soulagement apr\u00e8s l'effort.\n\nJe suis l'action et reste attentif \u00e0 ce qui l'entoure. D\u00e9termination, complicit\u00e9 et c\u00e9l\u00e9bration font partie de la m\u00eame histoire.",
            "contact_intro_en": "A race, a match, a story worth telling. Tell me what you're planning and which moments matter most to you.",
            "contact_intro_fr": "Une course, un match, une histoire \u00e0 raconter. Parlez-moi de votre projet et des moments qui comptent pour vous.",
        })
        for order, (slug, en, fr) in enumerate(CATEGORIES):
            Category.objects.get_or_create(slug=slug, defaults={"name_en": en, "name_fr": fr, "order": order})
        self.stdout.write(self.style.SUCCESS("Site settings and categories are ready. Existing content was preserved."))
