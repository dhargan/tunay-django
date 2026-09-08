/* geoplate — Turkish license plate code guessing game.
 *
 * The polygons come from the static enriched GeoJSON; the backend only ever
 * sees plate codes.
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

    var FLASH_MS = 700;
    var NEXT_PLATE_DELAY_MS = 1100;

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
        var $feedback = $('#feedback');
        var $modeBadge = $('#modeBadge');
        var $hardModeToggle = $('#hardModeToggle');

        var askedPlateCode = parseInt($map.data('plate-code'), 10);
        var hardMode = false;
        var locked = false;
        var provinceLayers = [];
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

        function flash(layer, style) {
            layer.setStyle(style);
            layer.bringToFront();
            window.setTimeout(function () {
                layer.setStyle(STYLE_DEFAULT);
            }, FLASH_MS);
        }

        function showPlate(plateCode, display) {
            askedPlateCode = plateCode;
            $plate.text(display);
        }

        function loadNextPlate() {
            $.getJSON(urls.randomPlate, { exclude: askedPlateCode })
                .done(function (data) {
                    showPlate(data.plate_code, data.plate_code_display);
                    setFeedback('Haritadan bir il seç.');
                })
                .fail(function () {
                    setFeedback('Yeni plaka kodu alınamadı, tekrar dene.', 'wrong');
                })
                .always(function () {
                    locked = false;
                });
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
            $.ajax({
                url: urls.checkAnswer,
                method: 'POST',
                dataType: 'json',
                contentType: 'application/json',
                headers: { 'X-CSRFToken': csrfToken },
                data: JSON.stringify({
                    asked_plate_code: askedPlateCode,
                    clicked_plate_code: clickedPlateCode
                })
            }).done(function (data) {
                if (data.correct) {
                    flash(layer, STYLE_CORRECT);
                    bumpCounter('#correctCount');
                    setFeedback('Doğru! ' + (data.city_name || ''), 'correct');
                    window.setTimeout(loadNextPlate, NEXT_PLATE_DELAY_MS);
                } else {
                    flash(layer, STYLE_WRONG);
                    bumpCounter('#wrongCount');
                    setFeedback('Yanlış, tekrar dene.', 'wrong');
                    locked = false;
                }
            }).fail(function () {
                setFeedback('Cevap kontrol edilemedi, tekrar dene.', 'wrong');
                locked = false;
            });
        }

        function onEachFeature(feature, layer) {
            provinceLayers.push(layer);
            applyTooltip(layer);

            layer.on({
                mouseover: function () {
                    layer.setStyle(STYLE_HOVER);
                    layer.bringToFront();
                },
                mouseout: function () {
                    layer.setStyle(STYLE_DEFAULT);
                },
                click: function () {
                    handleProvinceClick(layer);
                }
            });
        }

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
