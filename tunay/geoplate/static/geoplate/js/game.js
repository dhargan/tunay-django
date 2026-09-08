/* geoplate — Turkish license plate code guessing game.
 *
 * The polygons come from the static enriched GeoJSON; the backend only ever
 * sees plate codes. The backend also owns the attempt budget: it reveals the
 * answer only once the player has burned every attempt.
 */
(function ($) {
    'use strict';

    var STYLE_DEFAULT = {
        color: '#ffffff',
        weight: 1,
        fillColor: '#b79cbb',
        fillOpacity: 0.9
    };
    var STYLE_HOVER = { fillColor: '#8b6b8f', weight: 2, color: '#ffd700' };
    var STYLE_CORRECT = { fillColor: '#4caf50', weight: 2, color: '#2e7d32' };
    var STYLE_WRONG = { fillColor: '#d9534f', weight: 2, color: '#c0392b' };
    var STYLE_REVEAL = { fillColor: '#8b6b8f', weight: 3, color: '#ffd700' };

    var FLASH_MS = 700;
    var NEXT_PLATE_DELAY_MS = 1100;
    var REVEAL_DELAY_MS = 2600;

    $(function () {
        var $map = $('#map');
        if (!$map.length) {
            return;
        }

        var urls = {
            geojson: $map.data('geojson-url'),
            checkAnswer: $map.data('check-answer-url'),
            randomPlate: $map.data('random-plate-url')
        };

        var $plate = $('#plateDisplay');
        var $attempts = $('#attempts');
        var $feedback = $('#feedback');
        var $modeBadge = $('#modeBadge');
        var $hardModeToggle = $('#hardModeToggle');

        var askedPlateCode = parseInt($map.data('plate-code'), 10);
        var maxAttempts = parseInt($map.data('max-attempts'), 10) || 3;
        var attemptsUsed = 0;
        var hardMode = false;
        var locked = false;
        var provinceLayers = [];
        var layersByPlateCode = {};
        var revealedLayer = null;
        var csrfToken = $('#csrfForm input[name="csrfmiddlewaretoken"]').val();

        var map = L.map('map', {
            zoomControl: true,
            attributionControl: false,
            scrollWheelZoom: true
        });

        function setFeedback(message, state) {
            $feedback.removeClass('correct wrong').text(message);
            if (state) {
                $feedback.addClass(state);
            }
        }

        function renderAttempts(attemptsLeft) {
            var hearts = '';
            for (var i = 0; i < maxAttempts; i += 1) {
                hearts += i < attemptsLeft
                    ? '<i class="fas fa-heart"></i>'
                    : '<i class="fas fa-heart spent"></i>';
            }
            $attempts.html(hearts);
        }

        function bumpCounter(selector) {
            var $counter = $(selector);
            $counter.text(parseInt($counter.text(), 10) + 1);
        }

        function applyTooltip(layer) {
            var name = layer.feature.properties.name;
            if (hardMode || !name) {
                layer.unbindTooltip();
                return;
            }
            layer.bindTooltip(name, {
                sticky: true,
                direction: 'top',
                className: 'province-tooltip'
            });
        }

        function baseStyle(layer) {
            return layer === revealedLayer ? STYLE_REVEAL : STYLE_DEFAULT;
        }

        function flash(layer, style, duration) {
            layer.setStyle(style);
            layer.bringToFront();
            window.setTimeout(function () {
                layer.setStyle(baseStyle(layer));
            }, duration || FLASH_MS);
        }

        function loadNextPlate() {
            $.getJSON(urls.randomPlate, { exclude: askedPlateCode })
                .done(function (data) {
                    askedPlateCode = data.plate_code;
                    attemptsUsed = 0;
                    maxAttempts = data.max_attempts || maxAttempts;
                    $plate.text(data.plate_code_display);
                    renderAttempts(maxAttempts);
                    setFeedback('Haritadan bir il seç. ' + maxAttempts + ' hakkın var.');
                })
                .fail(function () {
                    setFeedback('Yeni plaka kodu alınamadı, tekrar dene.', 'wrong');
                })
                .always(function () {
                    locked = false;
                });
        }

        function revealAnswer(cityName, plateCode) {
            var answerLayer = layersByPlateCode[plateCode];
            if (answerLayer) {
                revealedLayer = answerLayer;
                answerLayer.setStyle(STYLE_REVEAL);
                answerLayer.bringToFront();
                window.setTimeout(function () {
                    revealedLayer = null;
                    answerLayer.setStyle(STYLE_DEFAULT);
                }, REVEAL_DELAY_MS);
            }
            renderAttempts(0);
            bumpCounter('#wrongCount');
            setFeedback(
                'Hakların bitti! Doğru cevap: ' + (cityName || '—'),
                'wrong'
            );
            window.setTimeout(loadNextPlate, REVEAL_DELAY_MS);
        }

        function handleProvinceClick(layer) {
            if (locked) {
                return;
            }
            var clickedPlateCode = layer.feature.properties.plate_code;
            if (!clickedPlateCode) {
                setFeedback('Bu il için plaka kodu bulunamadı.', 'wrong');
                return;
            }

            locked = true;
            attemptsUsed += 1;

            $.ajax({
                url: urls.checkAnswer,
                method: 'POST',
                dataType: 'json',
                contentType: 'application/json',
                headers: { 'X-CSRFToken': csrfToken },
                data: JSON.stringify({
                    asked_plate_code: askedPlateCode,
                    clicked_plate_code: clickedPlateCode,
                    attempt: attemptsUsed
                })
            }).done(function (data) {
                if (data.correct) {
                    flash(layer, STYLE_CORRECT);
                    bumpCounter('#correctCount');
                    setFeedback('Doğru! ' + (data.city_name || ''), 'correct');
                    window.setTimeout(loadNextPlate, NEXT_PLATE_DELAY_MS);
                    return;
                }

                flash(layer, STYLE_WRONG);

                if (data.attempts_left > 0) {
                    renderAttempts(data.attempts_left);
                    setFeedback(
                        'Yanlış! ' + data.attempts_left + ' hakkın kaldı.',
                        'wrong'
                    );
                    locked = false;
                    return;
                }

                revealAnswer(data.city_name, data.plate_code || askedPlateCode);
            }).fail(function () {
                attemptsUsed -= 1;
                setFeedback('Cevap kontrol edilemedi, tekrar dene.', 'wrong');
                locked = false;
            });
        }

        function onEachFeature(feature, layer) {
            provinceLayers.push(layer);
            if (feature.properties.plate_code) {
                layersByPlateCode[feature.properties.plate_code] = layer;
            }
            applyTooltip(layer);

            layer.on({
                mouseover: function () {
                    layer.setStyle(STYLE_HOVER);
                    layer.bringToFront();
                },
                mouseout: function () {
                    layer.setStyle(baseStyle(layer));
                },
                click: function () {
                    handleProvinceClick(layer);
                }
            });
        }

        renderAttempts(maxAttempts);

        $.getJSON(urls.geojson)
            .done(function (collection) {
                var layer = L.geoJSON(collection, {
                    style: STYLE_DEFAULT,
                    onEachFeature: onEachFeature
                }).addTo(map);
                map.fitBounds(layer.getBounds(), { padding: [12, 12] });
            })
            .fail(function () {
                setFeedback(
                    'Harita yüklenemedi. "manage.py generate_plate_geojson" komutunu çalıştırdın mı?',
                    'wrong'
                );
            });

        $hardModeToggle.on('change', function () {
            hardMode = this.checked;
            $modeBadge
                .toggleClass('hard', hardMode)
                .text(hardMode ? 'Zor mod' : 'Normal mod');
            $.each(provinceLayers, function (_, layer) {
                applyTooltip(layer);
            });
        });

        $('#skipButton').on('click', function () {
            if (locked) {
                return;
            }
            locked = true;
            loadNextPlate();
        });
    });
}(jQuery));
