window.styleBenchName = "StyleBenchConservative";

// This function ought be as simple as possible. Don't even use SimplePromise.
BenchmarkRunner.prototype._runTest = function(suite, test, prepareReturnValue, callback)
{
    var self = this;
    var now = window.performance && window.performance.now ? function () { return window.performance.now(); } : Date.now;

    var contentWindow = self._frame.contentWindow;
    var contentDocument = self._frame.contentDocument;

    // Force style resolution and layout before running the test to ensure we don't measure stuff unrelated to the test.
    window._unusedBackgroundColorValue = contentWindow.getComputedStyle(contentDocument.body).backgroundColor;
    window._unusedHeightValue = contentDocument.body.getBoundingClientRect().height;

    self._writeMark(suite.name + '.' + test.name + '-start');

    var startTime = now();
    test.run(prepareReturnValue, contentWindow, contentDocument);
    // Force style resolution + layout to ensure we're measuring it. Reading a computed color forces style resolution
    // even when the engine knows the pending style changes cannot affect geometry.
    window._unusedBackgroundColorValue = contentWindow.getComputedStyle(contentDocument.body).backgroundColor;
    window._unusedHeightValue = contentDocument.body.getBoundingClientRect().height;
    var endTime = now();

    self._writeMark(suite.name + '.' + test.name + '-sync-end');

    var syncTime = endTime - startTime;
    setTimeout(function () {
        var asyncTime = 1;
        self._writeMark(suite.name + '.' + test.name + '-async-end');
        callback(syncTime, asyncTime);
    }, 0);
}
