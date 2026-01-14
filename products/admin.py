from django.contrib import admin
from .models import Category, Product, BOM, BOMItem

# 1. Kategori Kaydı
@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name',)

# 2. Reçete Satırları (Inline - İç İçe Görünüm)
class BOMItemInline(admin.TabularInline):
    model = BOMItem
    extra = 1  # Varsayılan olarak kaç boş satır görünsün?
    autocomplete_fields = ['child_product'] # Ürünler arasından arayarak bulmak için

# 3. Reçete Başlığı
@admin.register(BOM)
class BOMAdmin(admin.ModelAdmin):
    list_display = ('parent_product', 'description')
    inlines = [BOMItemInline] # Reçete satırlarını bu ekrana gömüldü.
    search_fields = ['parent_product__name', 'parent_product__sku']

# 4. Ürün Kaydı
@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('sku', 'name', 'product_type', 'stock_quantity', 'price')
    list_filter = ('product_type', 'category')
    search_fields = ('name', 'sku')
