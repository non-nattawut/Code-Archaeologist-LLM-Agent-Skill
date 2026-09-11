<?php
// Laravel route table: verb routes, a prefix group, a resource cut down with only(), the legacy
// 'Controller@action' string, and a route to a controller that exists nowhere -- which must
// produce no route at all.
// Größe — 寸法 📦: non-ASCII before the table, so its line numbers are exercised too.
use App\Http\Controllers\OrderController;
use Illuminate\Support\Facades\Route;

Route::get('/orders', [OrderController::class, 'index']);
Route::post('/orders', 'OrderController@store');
Route::prefix('admin')->group(function () {
    Route::get('/reports', [ReportController::class, 'summary']);
});
Route::resource('invoices', InvoiceController::class)->only(['index', 'show']);
Route::get('/missing', [GhostController::class, 'boo']);
