# Helferregistrierung im lokalen Einsatznetz

Die Helferregistrierung arbeitet vollständig offline. QR-Bilder und Scanner-Rohdaten werden nur im Browser beziehungsweise für die unmittelbare Validierung verarbeitet und nicht gespeichert.

## HTTPS für Handykameras

Browser geben `getUserMedia()` auf einer LAN-Adresse nur in einem vertrauenswürdigen HTTPS-Kontext frei. `http://localhost:5000` funktioniert auf dem FLOW-PC, `http://192.168.x.x:5000` auf einem Handy dagegen nicht.

1. Dem FLOW-Server eine feste IP oder einen festen lokalen DNS-Namen geben.
2. Mit der lokalen Einsatzstellen-CA ein Serverzertifikat ausstellen. IP beziehungsweise DNS-Name müssen im Subject Alternative Name des Zertifikats stehen.
3. CA-Zertifikat einmalig auf den verwendeten Handys installieren und dort als vertrauenswürdig aktivieren.
4. Zertifikat und privaten Schlüssel außerhalb des Repositorys ablegen, beispielsweise unter `data/tls/`.
5. In `.env` konfigurieren:

   ```text
   FLOW_TLS_CERT=data/tls/flow-server.crt
   FLOW_TLS_KEY=data/tls/flow-server.key
   ```

6. FLOW neu starten und die HTTPS-Adresse auf dem Handy öffnen. Beim ersten Scan muss die Kameraberechtigung bestätigt werden.

Ohne vertrauenswürdiges HTTPS bleibt der Button für die Live-Kamera deaktiviert. Tastatur-/Bluetoothscanner und der lokale Bildimport bleiben verfügbar. Ein bloßes Fortsetzen nach einer Zertifikatswarnung gilt je nach Browser nicht als vertrauenswürdiger Kontext.

## Scannerbetrieb

- USB- und Bluetoothscanner müssen sich als Tastatur verhalten und den Scan mit Enter abschließen.
- Für Mobilgeräte wird die Rückkamera bevorzugt; weitere erkannte Kameras können im Dialog ausgewählt werden.
- Unterstützte Bilddateien: PNG, JPG/JPEG und BMP.
- Personen werden innerhalb einer Lage anhand Nachname, Vorname und Geburtsdatum zusammengeführt.
