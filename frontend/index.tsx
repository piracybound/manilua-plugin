import { initI18n, t } from './i18n';

declare const Millennium: {
    callServerMethod: (methodName: string, args?: Record<string, unknown>) => Promise<any>;
};
declare const ShowConfirmDialog: ((title: string, message: string) => any) | undefined;
declare const ShowAlertDialog: ((title: string, message: string) => any) | undefined;

type BackendResponse<T = Record<string, unknown>> = {
    success: boolean;
    error?: string;
} & T;

interface ApiStatus {
    hasKey: boolean;
    isValid: boolean;
    maskedKey: string;
    checked: boolean;
    message?: string;
}

interface DownloadModal {
    update: (text: string) => void;
    close: (delay?: number) => void;
}

const apiState: ApiStatus = {
    hasKey: false,
    isValid: false,
    maskedKey: '',
    checked: false,
};

let isBusy = false;

function backendLog(message: string) {
    try {
        if (typeof Millennium?.callServerMethod === 'function') {
            Millennium.callServerMethod('Logger.log', { message: String(message) }).catch(() => undefined);
        }
    } catch (error) {
        console.warn('[manilua] backendLog failed', error);
    }
}

async function callBackend<T = any>(method: string, args?: Record<string, unknown>): Promise<T> {
    try {
        const result = args === undefined
            ? await Millennium.callServerMethod(method)
            : await Millennium.callServerMethod(method, args);

        if (typeof result === 'string') {
            try {
                return JSON.parse(result) as T;
            } catch {
                return result as unknown as T;
            }
        }

        return result as T;
    } catch (error) {
        backendLog(`Backend call failed: ${method} - ${String(error)}`);
        throw error;
    }
}

async function getApiStatus(force = false): Promise<ApiStatus> {
    if (apiState.checked && !force) {
        return { ...apiState };
    }

    try {
        const status = await callBackend<BackendResponse<{ hasKey?: boolean; maskedKey?: string; isValid?: boolean; message?: string }>>('GetAPIKeyStatus');

        if (status?.success) {
            apiState.hasKey = Boolean(status.hasKey);
            apiState.isValid = status.isValid !== false;
            apiState.maskedKey = status.maskedKey ?? '';
            apiState.message = status.message;
        } else {
            apiState.hasKey = false;
            apiState.isValid = false;
            apiState.maskedKey = '';
            apiState.message = status?.error ?? 'API key status unavailable';
        }

        apiState.checked = true;
    } catch (error) {
        apiState.hasKey = false;
        apiState.isValid = false;
        apiState.maskedKey = '';
        apiState.message = String(error);
        apiState.checked = true;
    }

    return { ...apiState };
}

function findButtonContainer(): Element | null {
    const selectors = [
        '.game_area_purchase_game_wrapper .game_purchase_action_bg',
        '.game_area_purchase_game:not(.demo_above_purchase) .game_purchase_action_bg',
        '.game_area_purchase_game:not(.demo_above_purchase) .game_purchase_action',
        '.game_area_purchase_game:not(.demo_above_purchase) .btn_addtocart',
        '.game_area_purchase_game_wrapper',
        '.game_purchase_action_bg',
        '.game_purchase_action',
        '.btn_addtocart',
        '[class*="purchase"]',
    ];

    for (const selector of selectors) {
        const element = document.querySelector(selector);
        if (element) {
            if (selector.endsWith('.btn_addtocart')) {
                return element.parentElement;
            }
            return element;
        }
    }

    return null;
}

function getCurrentAppId(): number | null {
    const urlMatch = window.location.href.match(/\/app\/(\d+)/);
    if (urlMatch) {
        return parseInt(urlMatch[1], 10);
    }

    const dataAppId = document.querySelector('[data-appid]');
    if (dataAppId) {
        const value = dataAppId.getAttribute('data-appid');
        if (value) {
            const parsed = parseInt(value, 10);
            if (!Number.isNaN(parsed)) {
                return parsed;
            }
        }
    }

    return null;
}

function showDownloadModal(initialTextKey: string = 'status.downloading'): DownloadModal {
    let pendingText = t(initialTextKey);

    let overlay: HTMLElement | null = null;
    let content: HTMLElement | null = null;
    let messageEl: HTMLElement | null = null;
    let closed = false;

    const buildDom = () => {
        if (closed) {
            return;
        }

        if (!overlay) {
            overlay = document.querySelector('.newmodal[data-manilua-modal="download"]') as HTMLElement | null;
        }

        if (!overlay) {
            const activeModal = document.querySelector('.newmodal') as HTMLElement | null;
            if (activeModal) {
                activeModal.setAttribute('data-manilua-modal', 'download');
                overlay = activeModal;
            }
        }

        if (!overlay) {
            return;
        }

        if (!content) {
            content = overlay.querySelector('.newmodal_content') as HTMLElement | null;
            if (!content) {
                content = document.createElement('div');
                overlay.appendChild(content);
            }
        }

        if (!content) {
            return;
        }

        if (!messageEl) {
            content.innerHTML = '';

            messageEl = document.createElement('div');
            messageEl.style.minHeight = '40px';
            messageEl.style.display = 'flex';
            messageEl.style.alignItems = 'center';
            messageEl.style.color = '#ffffff';
            messageEl.textContent = pendingText;
            content.appendChild(messageEl);
        } else {
            messageEl.textContent = pendingText;
        }
    };

    const ensureDom = () => {
        buildDom();
        if (!messageEl) {
            setTimeout(buildDom, 120);
        }
    };

    const update = (text: string) => {
        pendingText = text;
        if (closed) {
            return;
        }
        if (!messageEl) {
            ensureDom();
        }
        if (messageEl) {
            messageEl.textContent = text;
        }
    };


    const close = (delay = 0) => {
        if (closed) {
            return;
        }
        closed = true;

        setTimeout(() => {
            try {
                const modalApi = (window as unknown as { CModal?: { DismissActiveModal?: () => void } }).CModal;
                if (overlay && overlay.matches('.newmodal[data-manilua-modal="download"]') && modalApi?.DismissActiveModal) {
                    modalApi.DismissActiveModal();
                } else if (overlay && typeof overlay.remove === 'function') {
                    overlay.remove();
                }
            } catch {
                if (overlay && typeof overlay.remove === 'function') {
                    overlay.remove();
                }
            }
        }, Math.max(0, delay));
    };

    if (typeof ShowAlertDialog === 'function') {
        try {
            ShowAlertDialog(t('auth.title'), pendingText);
        } catch (error) {
            console.warn('manilua: failed to open download modal via ShowAlertDialog', error);
        }
    } else {
        const fallbackOverlay = document.createElement('div');
        fallbackOverlay.setAttribute('data-manilua-modal', 'download');
        fallbackOverlay.style.position = 'fixed';
        fallbackOverlay.style.top = '0';
        fallbackOverlay.style.left = '0';
        fallbackOverlay.style.right = '0';
        fallbackOverlay.style.bottom = '0';
        fallbackOverlay.style.display = 'flex';
        fallbackOverlay.style.alignItems = 'center';
        fallbackOverlay.style.justifyContent = 'center';
        fallbackOverlay.style.background = 'rgba(0,0,0,0.6)';
        fallbackOverlay.style.zIndex = '10000';

        const panel = document.createElement('div');
        panel.style.background = '#1b2838';
        panel.style.border = '1px solid #67c1f5';
        panel.style.borderRadius = '4px';
        panel.style.padding = '18px';
        panel.style.minWidth = '280px';
        panel.style.color = '#ffffff';
        panel.style.fontFamily = 'sans-serif';

        messageEl = document.createElement('div');
        messageEl.textContent = pendingText;
        messageEl.style.marginBottom = '12px';

        const closeBtn = document.createElement('button');
        closeBtn.type = 'button';
        closeBtn.textContent = t('generic.close');
        closeBtn.style.marginTop = '12px';
        closeBtn.onclick = () => close(0);

        panel.appendChild(messageEl);
        panel.appendChild(closeBtn);
        fallbackOverlay.appendChild(panel);
        document.body.appendChild(fallbackOverlay);

        overlay = fallbackOverlay;
        content = panel;
    }

    ensureDom();

    return {
        update,
        close,
    };
}

function startProgressMonitoring(
    appId: number,
    modal: DownloadModal,
    options: {
        onDone: () => void;
        onFailed: (message?: string) => void;
        markIdle: () => void;
    }
) {
    let finished = false;

    const describeStatus = (state: Record<string, any>): string => {
        const rawStatus = typeof state.status === 'string' ? state.status.toLowerCase() : '';
        switch (rawStatus) {
            case 'checking':
                return state.currentApi
                    ? t('status.checkingApi', { api: state.currentApi })
                    : t('status.checking');
            case 'checking_availability':
                return t('status.checking');
            case 'queued':
                return t('status.queued');
            case 'downloading': {
                if (
                    typeof state.bytesRead === 'number' &&
                    typeof state.totalBytes === 'number' &&
                    state.totalBytes > 0
                ) {
                    const downloadedMb = (state.bytesRead / (1024 * 1024)).toFixed(1);
                    const totalMb = (state.totalBytes / (1024 * 1024)).toFixed(1);
                    const percent = Math.min(
                        100,
                        Math.max(0, Math.floor((state.bytesRead / state.totalBytes) * 100))
                    );
                    return `${t('status.downloadingProgress', {
                        downloaded: downloadedMb,
                        total: totalMb,
                    })} (${percent}%)`;
                }
                return t('status.downloading');
            }
            case 'processing':
                return t('status.processing');
            case 'extracting':
                return typeof state.extractedFiles === 'number'
                    ? t('status.extractingCount', { count: state.extractedFiles })
                    : t('status.extracting');
            case 'installing': {
                if (Array.isArray(state.installedFiles) && state.installedFiles.length > 0) {
                    return `${t('status.installing')} ${state.installedFiles[state.installedFiles.length - 1]}`;
                }
                if (typeof state.installedPath === 'string') {
                    const parts = state.installedPath.split(/[\\/]/);
                    return `${t('status.installing')} ${parts[parts.length - 1]}`;
                }
                return t('status.installing');
            }
            case 'done':
                return t('status.gameAdded');
            case 'failed':
                return state.error ? `${t('status.failed')}: ${state.error}` : t('status.failed');
            case 'auth_failed':
                return t('status.authFailed');
            default:
                if (typeof state.status === 'string' && state.status.trim() !== '') {
                    return state.status;
                }
                if (typeof state.message === 'string') {
                    return state.message;
                }
                return t('status.downloading');
        }
    };

    const finish = (callback: () => void) => {
        if (finished) {
            return;
        }
        finished = true;
        window.clearInterval(timer);
        try {
            callback();
        } finally {
            options.markIdle();
        }
    };

    const timer = window.setInterval(async () => {
        if (finished) {
            window.clearInterval(timer);
            return;
        }

        try {
            const payload = await callBackend<any>('GetStatus', { appid: appId });

            if (payload?.success === false) {
                const errorMessage = payload?.error ?? t('generic.error');
                modal.update(`${t('status.failed')}: ${errorMessage}`);
                modal.close(2500);
                finish(() => options.onFailed(errorMessage));
                return;
            }

            const state = payload?.state ?? payload;
            if (!state || typeof state !== 'object') {
                return;
            }

            const statusValue = typeof state.status === 'string' ? state.status.toLowerCase() : '';

            modal.update(describeStatus(state));

            if (statusValue === 'done') {
                modal.update(t('status.gameAdded'));
                modal.close(2000);
                finish(options.onDone);
            } else if (statusValue === 'auth_failed' || (state.requiresNewKey && statusValue === 'failed')) {
                modal.close(0);
                apiState.checked = false;
                apiState.hasKey = false;
                apiState.isValid = false;

                setTimeout(async () => {
                    const configured = await showApiKeyPrompt(appId);
                    if (!configured) {
                        finish(() => options.onFailed('API key required'));
                    } else {
                        finish(() => { });
                    }
                }, 100);

            } else if (statusValue === 'failed') {
                const errorMessage = state.error ?? t('generic.error');
                modal.update(`${t('status.failed')}: ${errorMessage}`);
                modal.close(2500);
                finish(() => options.onFailed(errorMessage));
            }
        } catch (error) {
            backendLog(`Progress monitoring error: ${String(error)}`);
        }
    }, 600);
}

async function showApiKeyPrompt(appId: number | null): Promise<boolean> {
    let attempts = 0;
    while (document.querySelector('.newmodal') && attempts < 10) {
        await new Promise(resolve => setTimeout(resolve, 100));
        attempts++;
    }

    if (document.querySelector('.newmodal')) {
        return false;
    }

    if (typeof ShowConfirmDialog !== 'function') {
        console.error('manilua: ShowConfirmDialog not available');
        return false;
    }

    try {
        const modal = ShowConfirmDialog(
            t('auth.title'),
            `${t('auth.getApiKey')}\n${t('auth.website')}`
        );

        if (!modal) {
            return false;
        }

        return await new Promise<boolean>((resolve) => {
            const cleanup = () => {
                const modalElement = document.querySelector('.newmodal[data-manilua-modal="api"]') ||
                    document.querySelector('.newmodal');
                if (modalElement instanceof HTMLElement) {
                    modalElement.style.display = 'none';
                    if (typeof modalElement.remove === 'function') {
                        modalElement.remove();
                    }
                }

                try {
                    if (modal && typeof modal.Dismiss === 'function') {
                        modal.Dismiss();
                    }
                } catch {
                    // ignore
                }
            };

            setTimeout(() => {
                const modalElement = document.querySelector('.newmodal');
                if (!modalElement) {
                    resolve(false);
                    return;
                }

                modalElement.setAttribute('data-manilua-modal', 'api');

                const content = modalElement.querySelector('.newmodal_content');
                const buttons = modalElement.querySelector('.newmodal_buttons');

                if (!content || !buttons) {
                    resolve(false);
                    return;
                }

                const description = document.createElement('div');
                description.style.marginBottom = '12px';
                description.textContent = t('auth.instructions');

                const input = document.createElement('input');
                input.type = 'text';
                input.placeholder = t('auth.placeholder');
                input.autocomplete = 'off';
                input.style.cssText = [
                    'width: 100%',
                    'padding: 8px 12px',
                    'background: rgba(0,0,0,0.4)',
                    'border: 1px solid #5c5c5c',
                    'border-radius: 3px',
                    'color: #ffffff',
                    'font-size: 14px',
                    'box-sizing: border-box',
                ].join(';');

                const helper = document.createElement('div');
                helper.style.marginTop = '8px';
                helper.style.fontSize = '12px';
                helper.style.opacity = '0.8';
                helper.textContent = t('auth.example');

                content.innerHTML = '';
                content.appendChild(description);
                content.appendChild(input);
                content.appendChild(helper);

                const buttonElements = Array.from(buttons.querySelectorAll('.btn_grey_steamui')) as HTMLElement[];

                const cancelButton = buttonElements.length > 1 ? buttonElements[0] : null;
                const saveButton = buttonElements.length > 1 ? buttonElements[1] : buttonElements[0] ?? null;

                if (cancelButton) {
                    cancelButton.innerHTML = `<span>${t('btn.cancel')}</span>`;
                    cancelButton.onclick = (event) => {
                        event.preventDefault();
                        cleanup();
                        resolve(false);
                    };
                }

                if (!saveButton) {
                    resolve(false);
                    return;
                }

                const setErrorMessage = (message: string) => {
                    helper.textContent = message;
                    helper.style.opacity = '1';
                    helper.style.color = '#ffa03b';
                };

                const setNormalMessage = () => {
                    helper.textContent = t('auth.example');
                    helper.style.opacity = '0.8';
                    helper.style.color = '';
                };

                setNormalMessage();

                saveButton.innerHTML = `<span>${t('auth.save')}</span>`;
                saveButton.onclick = async (event) => {
                    event.preventDefault();
                    event.stopPropagation();

                    const apiKey = input.value.trim();
                    if (!apiKey) {
                        input.style.borderColor = '#d94126';
                        input.focus();
                        setErrorMessage(t('auth.required'));
                        return;
                    }

                    input.style.borderColor = '#5c5c5c';
                    setNormalMessage();
                    saveButton.setAttribute('disabled', 'true');
                    saveButton.innerHTML = `<span>${t('auth.saving')}</span>`;

                    try {
                        const result = await callBackend<BackendResponse<{ message?: string }>>('SetAPIKey', { api_key: apiKey });
                        if (result?.success) {
                            apiState.checked = false;
                            cleanup();
                            resolve(true);

                            if (typeof appId === 'number') {
                                setTimeout(() => {
                                    const addButton = document.querySelector('[data-manilua-button] .btn_blue_steamui') as HTMLElement | null;
                                    addButton?.click();
                                }, 400);
                            }
                            return;
                        }

                        input.style.borderColor = '#d94126';
                        setErrorMessage(result?.error ?? t('auth.invalid'));
                    } catch (saveError) {
                        input.style.borderColor = '#d94126';
                        setErrorMessage(`${t('auth.error')}: ${String(saveError)}`);
                    } finally {
                        saveButton.removeAttribute('disabled');
                        saveButton.innerHTML = `<span>${t('auth.save')}</span>`;
                    }
                };

                input.addEventListener('keydown', (event) => {
                    if (event.key === 'Enter') {
                        event.preventDefault();
                        saveButton.click();
                    }
                });

                setTimeout(() => input.focus(), 150);
            }, 120);
        });
    } catch (error) {
        console.error('manilua: Failed to show API key prompt', error);
        return false;
    }
}

async function ensureApiKey(appId: number): Promise<boolean> {
    const status = await getApiStatus();

    if (!status.hasKey || status.isValid === false) {
        backendLog('API key missing or invalid, prompting user');
        const configured = await showApiKeyPrompt(appId);
        return configured;
    }

    return true;
}

async function startAddFlow(
    appId: number,
    button: HTMLElement,
    label: HTMLSpanElement,
    btnContainer: HTMLElement,
    resetButton: () => void,
    markIdle: () => void
): Promise<boolean> {
    backendLog(`Starting add flow for app ${appId}`);

    const hasKey = await ensureApiKey(appId);
    if (!hasKey) {
        resetButton();
        markIdle();
        return false;
    }

    label.textContent = t('btn.loading');
    button.style.opacity = '0.7';

    const modal = showDownloadModal();

    try {
        const result = await callBackend<BackendResponse<{ requiresNewKey?: boolean }>>('addViamanilua', { appid: appId });
        if (result?.success) {
            startProgressMonitoring(appId, modal, {
                onDone: () => {
                    btnContainer.remove();
                    setTimeout(() => {
                        injectGamePageButtons().catch((error) => backendLog(`Re-injection error: ${String(error)}`));
                    }, 250);
                },
                onFailed: () => {
                    resetButton();
                },
                markIdle,
            });
            return true;
        }

        if (result?.requiresNewKey) {
            backendLog('API key rejected during download start');
            apiState.checked = false;
            apiState.hasKey = false;
            apiState.isValid = false;
            modal.close();
            await showApiKeyPrompt(appId);
            markIdle();
            return false;
        }

        const errorMessage = result?.error ?? t('generic.error');
        backendLog(`Download failed: ${errorMessage}`);
        modal.update(`${t('status.failed')}: ${errorMessage}`);
        modal.close(2500);
        markIdle();
        return false;
    } catch (error) {
        const message = String(error);
        backendLog(`Download start error: ${message}`);
        modal.update(`${t('status.failed')}: ${message}`);
        modal.close(2500);
        markIdle();
        return false;
    }
}

async function startRemoveFlow(appId: number, button: HTMLElement, label: HTMLSpanElement): Promise<boolean> {
    backendLog(`Starting remove flow for app ${appId}`);

    try {
        const result = await callBackend<BackendResponse>('removeViamanilua', { appid: appId });
        if (result?.success) {
            backendLog('Game removed successfully from manilua');
            return true;
        }

        backendLog(`Failed to remove game: ${result?.error ?? t('generic.error')}`);
        label.textContent = t('btn.remove');
        button.style.opacity = '1';
        button.style.pointerEvents = 'auto';
        return false;
    } catch (error) {
        backendLog(`Remove error: ${String(error)}`);
        label.textContent = t('btn.remove');
        button.style.opacity = '1';
        button.style.pointerEvents = 'auto';
        return false;
    }
}

async function injectGamePageButtons() {
    const appId = getCurrentAppId();
    if (!appId || document.querySelector('[data-manilua-button]')) {
        return;
    }

    const container = findButtonContainer();
    if (!container) {
        return;
    }

    try {
        const status = await callBackend<BackendResponse<{ exists?: boolean }>>('hasluaForApp', { appid: appId });
        const hasLua = Boolean(status?.exists);

        const btnContainer = document.createElement('div');
        btnContainer.className = 'btn_addtocart btn_packageinfo';
        btnContainer.setAttribute('data-manilua-button', 'true');

        const button = document.createElement('span');
        button.setAttribute('role', 'button');
        button.className = 'btn_blue_steamui btn_medium';
        button.style.marginLeft = '2px';

        const buttonSpan = document.createElement('span');
        buttonSpan.textContent = hasLua ? t('btn.remove') : t('btn.add');
        button.appendChild(buttonSpan);
        btnContainer.appendChild(button);

        button.onclick = async (event) => {
            event.preventDefault();
            event.stopPropagation();

            if (isBusy) {
                return;
            }

            isBusy = true;

            const resetButton = () => {
                button.style.pointerEvents = 'auto';
                button.style.opacity = '1';
                buttonSpan.textContent = hasLua ? t('btn.remove') : t('btn.add');
            };

            if (hasLua) {
                button.style.pointerEvents = 'none';
                button.style.opacity = '0.7';
                buttonSpan.textContent = t('btn.removing');

                const removed = await startRemoveFlow(appId, button, buttonSpan);
                isBusy = false;

                if (removed) {
                    btnContainer.remove();
                    setTimeout(() => {
                        injectGamePageButtons().catch((error) => backendLog(`Re-injection error: ${String(error)}`));
                    }, 200);
                } else {
                    resetButton();
                }
                return;
            }

            button.style.pointerEvents = 'none';
            button.style.opacity = '0.7';
            buttonSpan.textContent = t('btn.loading');

            const flowStarted = await startAddFlow(
                appId,
                button,
                buttonSpan,
                btnContainer,
                resetButton,
                () => {
                    isBusy = false;
                }
            );

            if (!flowStarted) {
                resetButton();
            } else {
                buttonSpan.textContent = t('status.downloading');
            }
        };

        container.appendChild(btnContainer);
    } catch (error) {
        backendLog(`Failed to inject button: ${String(error)}`);
    }
}

let injectTimeout: number | null = null;

function debouncedInject() {
    if (injectTimeout) {
        clearTimeout(injectTimeout);
    }
    injectTimeout = setTimeout(() => {
        injectGamePageButtons().catch((error) => backendLog(`Inject error: ${String(error)}`));
    }, 200);
}

export default async function PluginMain() {
    await initI18n();

    setTimeout(() => {
        const observer = new MutationObserver(() => {
            if (window.location.href.includes('/app/')) {
                debouncedInject();
            }
        });

        observer.observe(document.body, { childList: true, subtree: true });
        injectGamePageButtons().catch((error) => backendLog(`Initial inject error: ${String(error)}`));
    }, 1000);
}
