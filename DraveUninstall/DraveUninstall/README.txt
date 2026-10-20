DraveUninstall - complete uninstaller (Dravenlock)
==================================================
Versie 0.2  -  de-installeren incl. restmappen + registersleutels, met back-up

Wat het doet
------------
Verwijdert geinstalleerde programma's compleet: eerst de eigen uninstaller, en
daarna de restmappen en registersleutels die Windows vaak laat staan. Maakt
eerst een back-up zodat je kunt herstellen. Alles lokaal en offline.

Starten
-------
  - Dubbelklik run.bat (installeert eenmalig zelf de omgeving).
  - Geen Windows? Dan draait de app in demonstratiestand met voorbeelddata.
  - Voor systeembrede programma's: start eventueel als administrator.

Zo werkt het
------------
  - 1) Kies een programma in de lijst (zoeken kan boven).
  - 2) Klik De-installeren. De eigen uninstaller start; doorloop die.
  - 3) Klik Restanten zoeken. Bekijk de gevonden mappen/sleutels, laat de
       back-up aan, en verwijder wat je echt weg wilt.
  - Back-ups...: een eerdere back-up terugzetten (mappen + registersleutels).
  - Geforceerde opruiming...: voor een al (deels) verwijderd programma -
    typ de naam en zoek direct naar restanten.
  - Je kunt meerdere programma's tegelijk selecteren (na elkaar).
  - De restantenlijst toont de grootte van elke restmap; de lijst toont
    ook de installatiedatum.

Is dit veilig?
--------------
Ja. DraveUninstall werkt lokaal en offline en stuurt niets naar internet.
Je antivirus of SmartScreen kan toch waarschuwen, omdat het een nieuw,
niet-ondertekend programma is dat bestanden verwijdert en het register
wijzigt - een vals alarm. Bij SmartScreen: Meer informatie, dan Toch uitvoeren.
Controleer de restantenlijst altijd zelf voordat je verwijdert.

Losse .exe maken (optioneel)
----------------------------
  - Dubbelklik bouw-exe.bat (gebruikt app.spec, PyInstaller).

Donatie (vrijwillig): paypal.me/roger076   Contact: service@dravenlock.nl
