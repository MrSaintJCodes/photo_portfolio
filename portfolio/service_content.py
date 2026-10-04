from django.db import models
from django.utils.translation import gettext as _, gettext_lazy


class ServiceKind(models.TextChoices):
    ATHLETE = "athlete-portraits", gettext_lazy("Individual athlete portraits")
    TEAM = "team-photos", gettext_lazy("Team and group photos")
    ACTION = "sports-action", gettext_lazy("Game-day action and training")
    RACE = "race-events", gettext_lazy("Races and endurance events")
    EVENT = "sports-events", gettext_lazy("Tournaments and sporting events")
    FITNESS = "fitness-promotion", gettext_lazy("Fitness and sports promotion")


SERVICES_HEADING_EN = "Sports photography for athletes, teams & events"
SERVICES_HEADING_FR = "Photographie sportive pour athl\u00e8tes, \u00e9quipes et \u00e9v\u00e9nements"
SERVICES_INTRO_EN = "From individual athlete portraits and team photos to game-day action, races, tournaments, and fitness sessions, I create images that capture the effort, energy, and people behind the sport. Based in Longueuil on Montr\u00e9al's South Shore, I work with athletes, teams, clubs, and event organizers to plan photography around what matters most to them."
SERVICES_INTRO_FR = "Des portraits d'athl\u00e8tes aux photos d'\u00e9quipe, en passant par l'action en comp\u00e9tition, les courses, les tournois et les s\u00e9ances d'entra\u00eenement, je cr\u00e9e des images qui racontent l'effort, l'\u00e9nergie et les personnes derri\u00e8re le sport. Bas\u00e9 \u00e0 Longueuil, sur la Rive-Sud de Montr\u00e9al, je travaille avec les athl\u00e8tes, les \u00e9quipes, les clubs et les organisateurs pour adapter la couverture photo \u00e0 leurs besoins."


def planning_steps():
    return [_("Tell me about the sport, people, location, and date."),
            _("We agree on the coverage, priorities, intended use, and delivery."),
            _("I photograph the planned portraits, action, or event."),
            _("You receive the image selection and format agreed for your project.")]


def audience_copy():
    return _("Individual athletes, teams and clubs, coaches, schools, fitness professionals, and event organizers.")


def booking_copy():
    return _("Whether you need portraits for one athlete, photos for an entire team, or coverage of a sporting event, tell me what you have in mind. Share the sport, date, location, and the moments or people you want photographed so we can discuss the right coverage.")
