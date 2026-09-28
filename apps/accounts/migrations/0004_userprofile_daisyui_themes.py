from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0003_userprofile_sidebar_mode"),
    ]

    operations = [
        migrations.AlterField(
            model_name="userprofile",
            name="theme",
            field=models.CharField(
                max_length=20,
                default="system",
                choices=[
                    ("system","System"),("light","Light"),("dark","Dark"),("cupcake","Cupcake"),
                    ("bumblebee","Bumblebee"),("emerald","Emerald"),("corporate","Corporate"),
                    ("synthwave","Synthwave"),("retro","Retro"),("cyberpunk","Cyberpunk"),
                    ("valentine","Valentine"),("halloween","Halloween"),("garden","Garden"),
                    ("forest","Forest"),("aqua","Aqua"),("lofi","Lo-fi"),("pastel","Pastel"),
                    ("fantasy","Fantasy"),("wireframe","Wireframe"),("black","Black"),("luxury","Luxury"),
                    ("dracula","Dracula"),("cmyk","CMYK"),("autumn","Autumn"),("business","Business"),
                    ("acid","Acid"),("lemonade","Lemonade"),("night","Night"),("coffee","Coffee"),
                    ("winter","Winter"),("dim","Dim"),("nord","Nord"),("sunset","Sunset"),
                    ("caramellatte","Caramellatte"),("abyss","Abyss"),("silk","Silk"),
                ],
            ),
        ),
    ]
