from django.contrib import admin
from .models import (
    Category, Product, BOM, BOMItem, WorkCenter, Operation,
    ProductionLog, ProductionOrder, Customer, SalesOrder,
    Shift, Warehouse, QualityCheck, Employee, StockTransaction,
    Maintenance, MaintenanceReason, QualityParameter, QualityMeasurement
)


admin.site.site_header = "KURUMSAL KAYNAK PLANLAMA YÖNETİM SİSTEMİ"
admin.site.index_title = "Yönetim Paneli"

# 1. INLINE) MODELLERİ
# Bu modeller, ana modelin içinde birer satır olarak görünür.
# Örneğin bir reçete açtığında, malzemeleri tek tek başka sayfaya gitmeden görebilirsin.

class BOMItemInline(admin.TabularInline):
    model = BOMItem
    extra = 1 # Varsayılan olarak 1 boş satır getir.
    autocomplete_fields = ['child_product'] # Binlerce ürün arasından arayarak seçmek için.

class OperationInline(admin.TabularInline):
    model = Operation
    extra = 1 # Reçete içine operasyon adımlarını gömer.

class QualityMeasurementInline(admin.TabularInline):
    model = QualityMeasurement
    extra = 1 # Kalite kontrol raporu içine ölçüm sonuçlarını gömer.

# --- 2. ÜRÜN VE REÇETE YÖNETİMİ ---

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    # list_display: Tablo listesinde hangi sütunların görüneceğini belirler.
    # stock_status: Models'de yazdığımız otonom özelliği burada sütun olarak görüyoruz.
    list_display = ('sku', 'name', 'product_type', 'stock_quantity', 'stock_status', 'price')
    # list_filter: Sağ tarafta hızlı filtreleme kutuları oluşturur.
    list_filter = ('product_type', 'category')
    # search_fields: Arama kutusunda hangi alanlarda arama yapılacağını belirler.
    search_fields = ('name', 'sku')

@admin.register(BOM)
class BOMAdmin(admin.ModelAdmin):
    list_display = ('parent_product', 'version', 'is_active')
    # inlines: Reçete içine hem malzemeleri hem operasyonları (rotayı) gömdük.
    inlines = [BOMItemInline, OperationInline]
    search_fields = ['parent_product__name']

# --- 3. ÜRETİM PLANLAMA VE SAHA TAKİBİ ---

@admin.register(ProductionOrder)
class ProductionOrderAdmin(admin.ModelAdmin):
    # current_progress ve is_delayed: Üretimin nabzını buradan tutuyoruz. - Otonom
    list_display = ('id', 'product', 'planned_quantity', 'current_progress', 'status', 'due_date', 'is_delayed')
    list_filter = ('status', 'start_date', 'due_date')
    # readonly_fields: Bu alanlar sistem tarafından hesaplandığı için elle değiştirilmesini engelledik.
    readonly_fields = ('current_progress', 'estimated_total_cost')

@admin.register(WorkCenter)
class WorkCenterAdmin(admin.ModelAdmin):
    # efficiency_factor: Makinenin otonom verimliliğini listede gösterir. - Otonom
    list_display = ('code', 'name', 'daily_capacity_hours', 'efficiency_factor', 'hourly_rate')

# --- 4. LOJİSTİK VE STOK HAREKETLERİ ---

@admin.register(StockTransaction)
class StockTransactionAdmin(admin.ModelAdmin):
    list_display = ('product', 'quantity', 'transaction_type', 'warehouse', 'created_at')
    list_filter = ('transaction_type', 'warehouse')
    # Veri girişini kolaylaştırmak için ürünleri aratıyoruz.
    autocomplete_fields = ['product']

# --- 5. DİĞER TEMEL KAYITLAR ---
# Basit kayıtlar için standart admin kaydı yeterlidir.

admin.site.register(Category)
admin.site.register(Customer)
admin.site.register(SalesOrder)
admin.site.register(Employee)
admin.site.register(Shift)
admin.site.register(Warehouse)
admin.site.register(QualityCheck)
admin.site.register(Maintenance)
admin.site.register(MaintenanceReason)
admin.site.register(ProductionLog)
admin.site.register(QualityParameter)