export const ConfirmationAction = Object.freeze({
    WAIT: 'wait',
    RETRY: 'retry',
    FINISH: 'finish',
});

export function rectMatches(left, right, tolerance = 1) {
    return Math.abs(left.x - right.x) <= tolerance &&
        Math.abs(left.y - right.y) <= tolerance &&
        Math.abs(left.width - right.width) <= tolerance &&
        Math.abs(left.height - right.height) <= tolerance;
}

export function isGridOrSizeMatch(observed, target, maxDeltaW = 20, maxDeltaH = 30) {
    const deltaX = Math.abs(observed.x - target.x);
    const deltaY = Math.abs(observed.y - target.y);
    const deltaW = Math.abs(observed.width - target.width);
    const deltaH = Math.abs(observed.height - target.height);
    return deltaX <= 4 && deltaY <= 4 && deltaW <= maxDeltaW && deltaH <= maxDeltaH;
}

export function isMinimumSizeMatch(observed, target, originalRect, tolerance = 1) {
    if (rectMatches(observed, originalRect, tolerance))
        return false;
    const targetCenterX = target.x + target.width / 2;
    const observedCenterX = observed.x + observed.width / 2;
    const centerMatches = Math.abs(observedCenterX - targetCenterX) <= Math.max(tolerance, (observed.width - target.width) / 2 + 4);
    const expandsWidth = observed.width >= target.width - tolerance;
    const expandsHeight = observed.height >= target.height - tolerance;
    return centerMatches && expandsWidth && expandsHeight;
}

export class MoveResizeConfirmation {
    constructor({
        target,
        originalRect,
        targetMonitor,
        tolerance = 1,
        requiredStableSamples = 2,
        maxPreviousGeometryRetries = 1,
        timeoutMs = 1_000,
    }) {
        this.target = target;
        this.originalRect = originalRect;
        this.targetMonitor = targetMonitor;
        this.tolerance = tolerance;
        this.requiredStableSamples = requiredStableSamples;
        this.maxPreviousGeometryRetries = maxPreviousGeometryRetries;
        this.timeoutMs = timeoutMs;
        this.stableSamples = 0;
        this.lastGeometry = null;
        this.retries = 0;
        this.finished = false;
    }

    get attempts() {
        return 1 + this.retries;
    }

    observe(sample, elapsedMs) {
        if (this.finished)
            throw new Error('confirmation already finished');
        if (sample.windowGone)
            return this._finish('window-gone');

        const onTargetMonitor = this.targetMonitor < 0 ||
            sample.monitor === this.targetMonitor;
        const unconstrainedState = !sample.maximizedHorizontally &&
            !sample.maximizedVertically && !sample.tiled;

        const isSameAsLast = this.lastGeometry !== null &&
            rectMatches(sample.geometry, this.lastGeometry, this.tolerance);
        this.lastGeometry = {...sample.geometry};

        if (isSameAsLast) {
            this.stableSamples += 1;
        } else {
            this.stableSamples = 1;
        }

        if (onTargetMonitor && unconstrainedState) {
            if (this.stableSamples >= this.requiredStableSamples) {
                if (rectMatches(sample.geometry, this.target, this.tolerance)) {
                    return this._finish('confirmed', null);
                } else if (isGridOrSizeMatch(sample.geometry, this.target)) {
                    return this._finish('confirmed', 'size-increments');
                } else if (isMinimumSizeMatch(sample.geometry, this.target, this.originalRect, this.tolerance)) {
                    return this._finish('confirmed', 'minimum-size');
                } else if (!rectMatches(sample.geometry, this.originalRect, this.tolerance)) {
                    const deltaW = Math.abs(sample.geometry.width - this.target.width);
                    const deltaH = Math.abs(sample.geometry.height - this.target.height);
                    const constraint = (deltaW <= 60 && deltaH <= 60)
                        ? 'size-increments'
                        : 'minimum-size';
                    return this._finish('confirmed', constraint);
                }
            }

            if (this.retries < this.maxPreviousGeometryRetries &&
                rectMatches(sample.geometry, this.originalRect, this.tolerance) &&
                !rectMatches(sample.geometry, this.target, this.tolerance)) {
                this.retries += 1;
                return {action: ConfirmationAction.RETRY, status: null, constraint: null};
            }
        } else {
            if (this.retries < this.maxPreviousGeometryRetries &&
                rectMatches(sample.geometry, this.originalRect, this.tolerance) &&
                !rectMatches(sample.geometry, this.target, this.tolerance)) {
                this.retries += 1;
                return {action: ConfirmationAction.RETRY, status: null, constraint: null};
            }
        }

        if (elapsedMs >= this.timeoutMs) {
            if (onTargetMonitor && unconstrainedState) {
                if (rectMatches(sample.geometry, this.target, this.tolerance))
                    return this._finish('confirmed', null);
                if (!rectMatches(sample.geometry, this.originalRect, this.tolerance) && this.stableSamples >= 1)
                    return this._finish('confirmed', 'minimum-size');
            }
            return this._finish('constraint-rejected');
        }
        return {action: ConfirmationAction.WAIT, status: null, constraint: null};
    }

    cancel() {
        if (this.finished)
            return {action: ConfirmationAction.FINISH, status: 'cancelled', constraint: null};
        return this._finish('cancelled');
    }

    _finish(status, constraint = null) {
        this.finished = true;
        return {action: ConfirmationAction.FINISH, status, constraint};
    }
}
