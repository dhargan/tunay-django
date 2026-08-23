(function ($) {
    const API = {
        dashboard: '/portfolio/api/dashboard/',
        transactions: '/portfolio/api/transactions/',
        assets: '/portfolio/api/assets/',
    };

    let monthlyPnlChart = null;
    let chartFilter = 'all';
    let historyFilter = 'all';
    let cachedTransactions = [];
    let liveRates = {};

    function matchesAssetFilter(tx, filter) {
        if (filter === 'usd') {
            return tx.asset && tx.asset.code === 'USD';
        }
        if (filter === 'gold') {
            return tx.asset && tx.asset.code === 'GA';
        }
        return true;
    }

    function getCookie(name) {
        const value = `; ${document.cookie}`;
        const parts = value.split(`; ${name}=`);
        if (parts.length === 2) {
            return parts.pop().split(';').shift();
        }
        return '';
    }

    function formatTRY(value, digits) {
        const amount = Number(value);
        if (Number.isNaN(amount)) {
            return '—';
        }
        return `${amount.toLocaleString('tr-TR', {
            minimumFractionDigits: digits,
            maximumFractionDigits: digits,
        })} ₺`;
    }

    function formatQty(value) {
        const amount = Number(value);
        if (Number.isNaN(amount)) {
            return '—';
        }
        return amount.toLocaleString('tr-TR', {
            minimumFractionDigits: 2,
            maximumFractionDigits: 4,
        });
    }

    function formatPct(value) {
        const amount = Number(value);
        if (Number.isNaN(amount)) {
            return '—';
        }
        const sign = amount > 0 ? '+' : '';
        return `${sign}${amount.toLocaleString('tr-TR', {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
        })}%`;
    }

    function renderLiveRate(code, quote) {
        const $price = $(`#liveRate${code}`);
        const $change = $(`#liveChange${code}`);
        if (!quote || quote.price == null) {
            $price.text('—');
            $change.text('—').removeClass('trend-up trend-down trend-neutral').addClass('trend-neutral');
            return;
        }
        $price.text(formatTRY(quote.price, 2));
        const pct = Number(quote.change_pct);
        const signedPct = `${pct > 0 ? '+' : ''}${pct.toLocaleString('tr-TR', {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
        })}%`;
        $change.removeClass('trend-up trend-down trend-neutral');
        if (quote.trend === 'up') {
            $change.addClass('trend-up').text(`▲ ${signedPct}`);
        } else if (quote.trend === 'down') {
            $change.addClass('trend-down').text(`▼ ${signedPct}`);
        } else {
            $change.addClass('trend-neutral').text(`- ${signedPct}`);
        }
    }

    function renderMonthlyPnlChart(payload) {
        const canvas = document.getElementById('monthlyPnlChart');
        if (!canvas || typeof Chart === 'undefined') {
            return;
        }
        const data = payload || { months: [], usd_pnl: [], ga_pnl: [] };
        if (monthlyPnlChart) {
            monthlyPnlChart.destroy();
        }
        monthlyPnlChart = new Chart(canvas, {
            type: 'line',
            data: {
                labels: data.months || [],
                datasets: [
                    {
                        label: 'ABD Doları',
                        data: data.usd_pnl || [],
                        borderColor: '#10B981',
                        backgroundColor: 'rgba(16, 185, 129, 0.12)',
                        tension: 0.3,
                        fill: false,
                        pointRadius: 4,
                    },
                    {
                        label: 'Gram altın',
                        data: data.ga_pnl || [],
                        borderColor: '#F59E0B',
                        backgroundColor: 'rgba(245, 158, 11, 0.12)',
                        tension: 0.3,
                        fill: false,
                        pointRadius: 4,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        onClick: Chart.defaults.plugins.legend.onClick,
                        labels: { color: '#333', font: { family: 'Quicksand' } },
                    },
                },
                scales: {
                    x: {
                        ticks: { color: '#666' },
                        grid: { color: '#ece6ee' },
                    },
                    y: {
                        ticks: {
                            color: '#666',
                            callback(value) {
                                return `${Number(value).toLocaleString('tr-TR')} ₺`;
                            },
                        },
                        grid: { color: '#ece6ee' },
                    },
                },
            },
        });
        applyChartFilter(chartFilter);
    }

    function applyChartFilter(filter) {
        if (!monthlyPnlChart) {
            return;
        }
        const showUsd = filter === 'all' || filter === 'usd';
        const showGold = filter === 'all' || filter === 'gold';
        monthlyPnlChart.setDatasetVisibility(0, showUsd);
        monthlyPnlChart.setDatasetVisibility(1, showGold);
        monthlyPnlChart.update();
    }

    function setActiveChartFilter(filter) {
        chartFilter = filter;
        $('.js-chart-filter').each(function () {
            const isActive = $(this).data('filter') === filter;
            $(this)
                .toggleClass('active', isActive)
                .toggleClass('btn-accent', isActive)
                .toggleClass('btn-outline-secondary', !isActive);
        });
        applyChartFilter(filter);
    }

    function setActiveHistoryFilter(filter) {
        historyFilter = filter;
        $('.js-tx-filter').each(function () {
            const isActive = $(this).data('filter') === filter;
            $(this)
                .toggleClass('active', isActive)
                .toggleClass('btn-accent', isActive)
                .toggleClass('btn-outline-secondary', !isActive);
        });
        renderTransactionHistory(cachedTransactions);
    }

    function pnlClass(value) {
        const amount = Number(value);
        if (amount > 0) {
            return 'pnl-positive';
        }
        if (amount < 0) {
            return 'pnl-negative';
        }
        return 'text-secondary';
    }

    function signedTRY(value) {
        const amount = Number(value);
        const formatted = formatTRY(Math.abs(amount), 2);
        if (amount > 0) {
            return `+${formatted}`;
        }
        if (amount < 0) {
            return `-${formatted}`;
        }
        return formatted;
    }

    function showToast(message, isError) {
        const $toast = $('#dashboardToast');
        $toast.find('.toast-body').text(message);
        $toast.removeClass('border-danger border-success');
        $toast.addClass(isError ? 'border-danger' : 'border-success');
        bootstrap.Toast.getOrCreateInstance($toast[0]).show();
    }

    function parseApiError(xhr) {
        const data = xhr.responseJSON;
        if (!data) {
            return xhr.statusText || 'İstek başarısız oldu.';
        }
        if (typeof data.detail === 'string') {
            return data.detail;
        }
        if (Array.isArray(data.detail)) {
            return data.detail.join(' ');
        }
        return Object.keys(data)
            .map((key) => {
                const value = data[key];
                if (Array.isArray(value)) {
                    return `${key}: ${value.join(' ')}`;
                }
                return `${key}: ${value}`;
            })
            .join(' ');
    }

    function loadDashboardData() {
        return $.getJSON(API.dashboard).done((data) => {
            $('#kpiTotalValue').text(formatTRY(data.current_total_value, 2));
            $('#kpiPnlTry')
                .text(signedTRY(data.total_pnl_try))
                .removeClass('pnl-positive pnl-negative text-secondary')
                .addClass(pnlClass(data.total_pnl_try));
            $('#kpiPnlPct')
                .text(formatPct(data.total_pnl_percentage))
                .removeClass('pnl-positive pnl-negative text-secondary')
                .addClass(pnlClass(data.total_pnl_percentage));
            $('#kpiTodayTry')
                .text(signedTRY(data.today_change_try))
                .removeClass('pnl-positive pnl-negative text-secondary')
                .addClass(pnlClass(data.today_change_try));
            $('#kpiTodayPct')
                .text(formatPct(data.today_change_percentage))
                .removeClass('pnl-positive pnl-negative text-secondary')
                .addClass(pnlClass(data.today_change_percentage));
            $('#kpiRealizedTry')
                .text(signedTRY(data.realized_pnl_try))
                .removeClass('pnl-positive pnl-negative text-secondary')
                .addClass(pnlClass(data.realized_pnl_try));
            const rates = data.live_rates || {};
            liveRates = rates;
            renderLiveRate('USD', rates.USD);
            renderLiveRate('GA', rates.GA);
            renderMonthlyPnlChart(data.monthly_pnl);
            renderAssetSummary(cachedTransactions);
        });
    }

    function isSell(tx) {
        return tx.transaction_type === 'SELL';
    }

    function buildAssetSummary(transactions) {
        const grouped = {};
        const ordered = [...(transactions || [])].sort((left, right) => {
            const dateCompare = String(left.transaction_date).localeCompare(
                String(right.transaction_date)
            );
            if (dateCompare !== 0) {
                return dateCompare;
            }
            return Number(left.id) - Number(right.id);
        });
        ordered.forEach((tx) => {
            const code = tx.asset.code;
            if (!grouped[code]) {
                grouped[code] = {
                    code,
                    name: tx.asset.name,
                    amount: 0,
                    cost: 0,
                    realized: 0,
                };
            }
            const qty = Number(tx.amount);
            const cash = Number(tx.total_paid_try);
            if (isSell(tx)) {
                const avg = grouped[code].amount ? grouped[code].cost / grouped[code].amount : 0;
                grouped[code].realized += (qty ? cash / qty - avg : 0) * qty;
                grouped[code].cost -= avg * qty;
                grouped[code].amount -= qty;
                if (grouped[code].amount <= 0) {
                    grouped[code].amount = 0;
                    grouped[code].cost = 0;
                }
            } else {
                grouped[code].amount += qty;
                grouped[code].cost += cash;
            }
        });
        return Object.values(grouped);
    }

    function unitPriceFor(row) {
        const quote = liveRates[row.code];
        if (quote && quote.price != null) {
            return Number(quote.price);
        }
        return null;
    }

    function renderAssetSummary(transactions) {
        const rows = buildAssetSummary(transactions);
        const $body = $('#assetSummaryBody').empty();
        if (!rows.length) {
            $body.append(
                '<tr class="empty-row"><td colspan="4">Henüz varlık özeti yok.</td></tr>'
            );
            return;
        }
        rows.forEach((row) => {
            const unitPrice = unitPriceFor(row);
            const totalValue =
                unitPrice != null ? unitPrice * row.amount : 0;
            const unrealized = totalValue - row.cost;
            const pnl = unrealized + row.realized;
            $body.append(`
                <tr>
                    <td>${row.name}</td>
                    <td>${formatQty(row.amount)}</td>
                    <td>${formatTRY(totalValue, 2)}</td>
                    <td class="${pnlClass(pnl)}">${signedTRY(pnl)}</td>
                </tr>
            `);
        });
    }

    function renderTransactionHistory(transactions) {
        const filtered = (transactions || []).filter((tx) =>
            matchesAssetFilter(tx, historyFilter)
        );
        const $body = $('#transactionHistoryBody').empty();
        if (!filtered.length) {
            const emptyMessage = transactions && transactions.length
                ? 'Bu filtreye uygun işlem yok.'
                : 'Henüz işlem yok.';
            $body.append(
                `<tr class="empty-row"><td colspan="9">${emptyMessage}</td></tr>`
            );
            return;
        }
        filtered.forEach((tx) => {
            const sell = isSell(tx);
            const typeLabel = sell ? 'Satış' : 'Alış';
            const typeClass = sell ? 'tx-badge-sell' : 'tx-badge-buy';
            const qty = sell ? -Number(tx.amount) : Number(tx.amount);
            const pnl = sell ? tx.realized_pnl : tx.pnl_try;
            $body.append(`
                <tr class="${sell ? 'tx-row-sell' : ''}">
                    <td>${tx.transaction_date}</td>
                    <td>${tx.asset.name}</td>
                    <td><span class="tx-badge ${typeClass}">${typeLabel}</span></td>
                    <td>${formatQty(qty)}</td>
                    <td>${formatTRY(tx.total_paid_try, 2)}</td>
                    <td>${formatTRY(tx.spread_fee_try || 0, 2)}</td>
                    <td>${sell ? '—' : formatTRY(tx.current_value, 2)}</td>
                    <td class="${pnlClass(pnl)}">${signedTRY(pnl)}</td>
                    <td class="text-nowrap">
                        <button type="button" class="action-btn js-edit-tx" data-id="${tx.id}" title="Düzenle">
                            <i class="fa-solid fa-pencil"></i>
                        </button>
                        <button type="button" class="action-btn danger js-delete-tx" data-id="${tx.id}" title="Sil">
                            <i class="fa-solid fa-trash"></i>
                        </button>
                    </td>
                </tr>
            `);
        });
    }

    function loadTransactions() {
        return $.getJSON(API.transactions).done((data) => {
            const transactions = Array.isArray(data) ? data : data.results || [];
            cachedTransactions = transactions;
            renderAssetSummary(transactions);
            renderTransactionHistory(transactions);
        });
    }

    function loadAssets() {
        return $.getJSON(API.assets).done((data) => {
            const assets = Array.isArray(data) ? data : data.results || [];
            const $select = $('#asset_code').empty();
            $select.append('<option value="">Varlık seçin</option>');
            assets.forEach((asset) => {
                $select.append(
                    `<option value="${asset.code}">${asset.name}</option>`
                );
            });
        });
    }

    function setSaveButtonBusy(busy) {
        $('#transactionSaveBtn').prop('disabled', busy);
    }

    function syncPaidLabel() {
        const isSellSelected = $('#transaction_type').val() === 'SELL';
        $('#totalPaidLabel').text(isSellSelected ? 'Tahsil (TRY)' : 'Ödenen (TRY)');
    }

    function resetTransactionForm() {
        $('#transactionId').val('');
        $('#transactionModalTitle').text('Yeni işlem');
        $('#formError').addClass('d-none').text('');
        $('#addTransactionForm')[0].reset();
        $('#transaction_type').val('BUY');
        $('#transaction_date').val(new Date().toISOString().slice(0, 10));
        setSaveButtonBusy(false);
        syncPaidLabel();
    }

    function transactionUrl(id) {
        return `${API.transactions}${id}/`;
    }

    function fillTransactionForm(tx) {
        $('#transactionId').val(tx.id);
        $('#transactionModalTitle').text('İşlemi düzenle');
        $('#asset_code').val(tx.asset && tx.asset.code);
        $('#transaction_type').val(tx.transaction_type || 'BUY');
        $('#amount').val(tx.amount);
        $('#total_paid_try').val(tx.total_paid_try);
        $('#transaction_date').val(tx.transaction_date);
        syncPaidLabel();
        bootstrap.Modal.getOrCreateInstance(
            document.getElementById('addTransactionModal')
        ).show();
    }

    function editTransaction(id) {
        const cached = cachedTransactions.find(
            (tx) => Number(tx.id) === Number(id)
        );
        return $.when(loadAssets())
            .then(() => {
                if (cached) {
                    fillTransactionForm(cached);
                    return;
                }
                return $.getJSON(transactionUrl(id)).done(fillTransactionForm);
            })
            .fail((xhr) => {
                showToast(parseApiError(xhr), true);
            });
    }

    function deleteTransaction(id) {
        if (!confirm('Bu işlemi silmek istediğinize emin misiniz?')) {
            return;
        }
        return $.ajax({
            url: transactionUrl(id),
            method: 'DELETE',
        })
            .done(() => {
                showToast('İşlem silindi.', false);
                reloadAll();
            })
            .fail((xhr) => {
                showToast(parseApiError(xhr), true);
            });
    }

    function reloadAll() {
        return $.when(loadDashboardData(), loadTransactions());
    }

    $(function () {
        $.ajaxSetup({
            headers: { 'X-CSRFToken': getCookie('csrftoken') },
        });

        $('#transaction_date').val(new Date().toISOString().slice(0, 10));

        loadAssets();
        reloadAll();

        $(document).on('change', '#transaction_type', syncPaidLabel);

        $(document).on('click', '.js-chart-filter', function () {
            setActiveChartFilter($(this).data('filter'));
        });

        $(document).on('click', '.js-tx-filter', function () {
            setActiveHistoryFilter($(this).data('filter'));
        });

        $(document).on('click', '.js-edit-tx', function () {
            editTransaction($(this).data('id'));
        });

        $(document).on('click', '.js-delete-tx', function () {
            deleteTransaction($(this).data('id'));
        });

        $('[data-bs-target="#addTransactionModal"]').on('click', function () {
            resetTransactionForm();
        });

        $('#addTransactionForm').on('submit', function (event) {
            event.preventDefault();
            if ($('#transactionSaveBtn').prop('disabled')) {
                return;
            }
            const $error = $('#formError').addClass('d-none').text('');
            const transactionId = $('#transactionId').val();
            const payload = {
                asset_code: $('#asset_code').val(),
                transaction_type: $('#transaction_type').val(),
                amount: $('#amount').val(),
                total_paid_try: $('#total_paid_try').val(),
                transaction_date: $('#transaction_date').val(),
            };

            setSaveButtonBusy(true);
            $.ajax({
                url: transactionId ? transactionUrl(transactionId) : API.transactions,
                method: transactionId ? 'PUT' : 'POST',
                contentType: 'application/json',
                data: JSON.stringify(payload),
            })
                .done(() => {
                    showToast(
                        transactionId ? 'İşlem güncellendi.' : 'İşlem kaydedildi.',
                        false
                    );
                    bootstrap.Modal.getInstance(
                        document.getElementById('addTransactionModal')
                    ).hide();
                    resetTransactionForm();
                    reloadAll();
                })
                .fail((xhr) => {
                    $error.removeClass('d-none').text(parseApiError(xhr));
                    setSaveButtonBusy(false);
                });
        });

        $('#addTransactionModal').on('hidden.bs.modal', () => {
            resetTransactionForm();
        });
    });
})(jQuery);
