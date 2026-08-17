export const MAX_CACHED_OPERATIONS = 256;

export function validateOperationId(value) {
    const id = String(value ?? '').trim();
    if (!id || id.length > 128)
        throw new TypeError('operation_id must contain 1 to 128 characters');
    return id;
}

export class OperationStore {
    constructor(limit = MAX_CACHED_OPERATIONS) {
        this._limit = limit;
        this._results = new Map();
        this._pending = new Map();
    }

    execute(operationId, fingerprint, callback) {
        const cached = this.lookup(operationId, fingerprint);
        if (cached)
            return cached;
        const pending = this.reserve(operationId, fingerprint);
        if (pending)
            return pending;
        const id = validateOperationId(operationId);
        let result;
        try {
            const value = callback();
            result = {
                operationId: id,
                accepted: true,
                errorCode: null,
                message: '',
                value: value ?? null,
                duplicate: false,
            };
        } catch (error) {
            result = {
                operationId: id,
                accepted: false,
                errorCode: error.code ?? 'operation-failed',
                message: error.message ?? String(error),
                value: null,
                duplicate: false,
            };
        }
        this.remember(id, fingerprint, result);
        return {...result};
    }

    // Las operaciones de Mutter que esperan un configure completan más tarde.
    // Estas dos primitivas conservan la misma semántica idempotente sin
    // bloquear el loop de GNOME Shell mientras se espera al cliente Wayland.
    lookup(operationId, fingerprint) {
        const id = validateOperationId(operationId);
        if (!this._results.has(id))
            return null;
        const cached = this._results.get(id);
        if (cached.fingerprint !== fingerprint) {
            return {
                operationId: id,
                accepted: false,
                errorCode: 'operation-id-conflict',
                message: 'operation_id was reused with different arguments',
                value: null,
                duplicate: true,
            };
        }
        return {...cached.result, duplicate: true};
    }

    remember(operationId, fingerprint, result) {
        const id = validateOperationId(operationId);
        this._pending.delete(id);
        this._results.set(id, {fingerprint, result: {...result, operationId: id}});
        while (this._results.size > this._limit)
            this._results.delete(this._results.keys().next().value);
    }

    clear() {
        this._results.clear();
        this._pending.clear();
    }

    // Reserva IDs para las operaciones asíncronas. Así ningún método D-Bus
    // puede reutilizar un ID mientras Mutter aún espera un configure.
    reserve(operationId, fingerprint) {
        const id = validateOperationId(operationId);
        const cached = this.lookup(id, fingerprint);
        if (cached)
            return cached;
        const pendingFingerprint = this._pending.get(id);
        if (pendingFingerprint !== undefined) {
            return {
                operationId: id,
                accepted: false,
                errorCode: pendingFingerprint === fingerprint
                    ? 'operation-pending'
                    : 'operation-id-conflict',
                message: pendingFingerprint === fingerprint
                    ? 'operation_id is still pending'
                    : 'operation_id was reused with different arguments',
                value: null,
                duplicate: true,
            };
        }
        this._pending.set(id, fingerprint);
        return null;
    }

    get size() {
        return this._results.size;
    }

    get pendingSize() {
        return this._pending.size;
    }
}
