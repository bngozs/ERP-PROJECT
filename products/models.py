from django.db import models # models veritabanı eklenir.
from decimal import Decimal # Matematiksel hassasiyet için eklenir.
from datetime import date

# Django'ya Category adında bir veritabanı tablosu oluşturtulur.
class Category(models.Model):
    # Kendi tablosuna bağlanarak hiyerarşik (Alt-Üst) kategori yapısı kurulur.
    parent = models.ForeignKey(
        'self',
        # CASCADE: Referans verilen nesne silindiğinde, ona referans veren nesneleri de silin.
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='subcategories',
        verbose_name="Üst Kategori"
    )
    # Kurumsal takip için benzersiz kategori kodu.
    code = models.CharField(max_length=20, unique=True, null=True, blank=True, verbose_name="Kategori Kodu")
    # Kategorinin adı ve maksimum uzunluğu bu kısımda ayarlanır.
    name = models.CharField(max_length=100, verbose_name="Kategori Adı")
    # Açıklama kısmı yazılır. Blank=True boş bırakabilir manasında.
    description = models.TextField(blank=True, null=True, verbose_name="Açıklama")
    # Kategorinin kullanımda olup olmadığını belirlenir.
    is_active = models.BooleanField(default=True, verbose_name="Aktif mi?")

    # Model ayarları yapılır. -Django İngilizce duyarlıdır.-
    class Meta:
        verbose_name = "Kategori"  # Tekil ismi
        verbose_name_plural = "Kategoriler"  # Çoğul ismi
        ordering = ['name']  # Listelerken her zaman isme göre sırala

# __str__ Admin panelinde bu kategoriyi gördüğünde kodu değil, isminin görülmesini sağlar.
    def __str__(self):
        return self.name


class Product(models.Model):
    # Ölçü Birimleri
    UOM_CHOICES = [
        ('UNIT', 'Adet'),
        ('KG', 'Kilogram'),
        ('LT', 'Litre'),
        ('METER', 'Metre'),
        ('M2', 'Metrekare'),
    ]

    PRODUCT_TYPES = [
        # 1. Temel Üretim Tipleri
        ('RAW', 'Raw Material (Hammadde)'),
        ('SEMI', 'Semi-Finished (Yarı Mamul)'),
        ('FINAL', 'Finished Good (Mamul)'),

        # 2. Ticari ve Destekleyici Tipler
        # TRAD: Üretimden geçmez. Direkt satın alınır ve satılır. Direkt "Satın Alma Talebi" olarak görür.
        ('TRAD', 'Trading Good (Ticari Mal)'),
        # CONS: Ürün ağacına (BOM) genelde girmez. Ancak stok seviyesi düştüğünde uyarı vermesi gerekir.
        ('CONS', 'Consumable (Sarf Malzeme)'),
        #MRO: Fabrikadaki makinelerin bakımı için gereken yedek parçalardır.
        ('MRO', 'MRO - Maintenance & Repair (İşletme Malzemesi)'),

        # 3. Hizmet ve Yan Ürünler
        # SRVC: Fiziksel stok tutulmaz. Nakliye bedeli veya dış fason işçilik gibi kalemleri ürün maliyetine eklemek için kullanılır.
        ('SRVC', 'Service (Hizmet)'),
        # SCRP: Üretim sonunda ortaya çıkar.
        ('SCRP', 'Scrap/Waste (Hurda/Atık)'),
        # Lojistik planlamasında ürünün hacmi ve paketleme malzemesi ihtiyacı için kritiktir.
        ('PACK', 'Packaging (Paketleme Malzemesi)'),
    ]

    # ForeignKey: Bu ürünün, daha önce tanımladığımız Category tablosundan birine ait olduğunu söyler.
    # on_delete=models.SET_NULL: Bir kategori silinince o kategoriye ait verilerin silinmesini önler. set null: boş bırak
    # Related_name: Bir kategori üzerinden o kategoriye ait tüm ürünlere -category.products.all()- tek komutla ulaşmanı sağlar.
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, related_name="products")

    # CharField: Kısa metinler için kullanılır.
    name = models.CharField(max_length=255, verbose_name="Ürün Adı")

    # sku (Stock Keeping Unit): Ürünün barkod numarası veya stok kodudur.
    # unique = True ile eşsiz olması yani aynı ürünün girilmesi engellenir.
    sku = models.CharField(max_length=50, unique=True, verbose_name="Stok Kodu (SKU)")

    # default='RAW': Eğer tip seçilmezse, sistem bunu otomatik olarak "Hammadde" olarak kaydeder.
    product_type = models.CharField(max_length=10, choices=PRODUCT_TYPES, default='RAW', verbose_name="Ürün Tipi")

    # DecimalField: FloatField bazen hassas hesaplamalarda hata yapabilir. Bu yüzden DecimalField kullanılır.
    price = models.DecimalField(max_digits=12, decimal_places=4, default=0, verbose_name="Birim Fiyat")
    stock_quantity = models.DecimalField(max_digits=12, decimal_places=4, default=0, verbose_name="Stok Miktarı")

    # MRP ve Planlama Parametreleri
    unit_of_measure = models.CharField(max_length=10, choices=UOM_CHOICES, default='UNIT', verbose_name="Ölçü Birimi")
    # Tedarik veya üretim süresi (Gün cinsinden). MRP hesaplamasında teslim tarihini bulmak için kullanılır.
    lead_time = models.PositiveIntegerField(default=0, verbose_name="Tedarik Süresi (Gün)")
    # Kritik stok seviyesi. Bu seviyenin altına düşülünce sistem uyarı verir.
    min_stock_level = models.DecimalField(max_digits=12, decimal_places=4, default=0, verbose_name="Minimum Stok Seviyesi")

    # Akıllı Talep Hesabı
    # Bu özellik, Net İhtiyacı otonomlaştırır.
    @property
    def net_requirement(self):
        """
        Net İhtiyaç = (Toplam Satış Siparişleri + Emniyet Stoku) - (Mevcut Stok + Devam Eden Üretim)
        Bu fonksiyon, MRP (Malzeme İhtiyaç Planlaması) içindir.
        """
        # 1. Sevk edilmemiş toplam müşteri talebi
        total_demand = sum(order.quantity for order in self.salesorder_set.filter(is_shipped=False))

        # 2. Şu an üretimde olan miktar
        in_production = sum(order.planned_quantity - order.actual_quantity for order in self.productionorder_set.filter(status__in=['PLANNED', 'IN_PROGRESS']))

        # Formülasyon
        requirement = (total_demand + self.min_stock_level) - (self.stock_quantity + in_production)
        return max(requirement, Decimal('0'))  # İhtiyaç negatif çıkamaz.


    # Otonom Stok Kontrolü
    @property
    def stock_status(self):
        """Ürünün stok miktarını kritik seviye ile kıyaslayarak durum raporu döner."""
        if self.stock_quantity <= 0:
            return "STOK TÜKENDİ"
        elif self.stock_quantity <= self.min_stock_level:
            return "KRİTİK SEVİYE"
        return "GÜVENLİ"

    # Otonom Rota Süresi Hesabı
    @property
    def calculated_production_time(self):
        """Operasyonlardaki süreleri ve makine verimliliklerini toplayarak gerçekçi üretim süresini (dakika) hesaplar."""
        if hasattr(self, 'bom_header'):
             total = sum(
                (op.setup_time + op.cycle_time) / op.work_center.efficiency_factor
                for op in self.bom_header.operations.all()
             )
        return round(total, 2)
        return 0


    def __str__(self):
        return f"[{self.get_product_type_display()}] {self.name}"

# Ürün Ağacı oluşturma
class BOM(models.Model):
    # OneToOneField: Bir ürünün sadece bir tane ana reçetesi olabilir.
    # Eğer ForeignKey kullansaydık, bir bisiklet için 5 farklı reçete tanımlanabilirdi.
    parent_product = models.OneToOneField(
        Product,
        # Eğer ana ürün sistemden silinirse, ona bağlı olan bu reçete kartı da otomatik olarak silinir.
        on_delete=models.CASCADE,
        # bom_header: Ürün üzerinden reçeteye ulaşmak istediğinde kullanacağın isimdir.
        related_name="bom_header",
        # BOM oluştururken kullanıcıya sadece Yarı Mamul (SEMI) ve Mamullar (FINAL) listesini göster.
        # Hammadde (RAW) dışarıdan satın alındığı için onun bir reçetesi olamaz.
        limit_choices_to={'product_type__in': ['SEMI', 'FINAL']},
        verbose_name="Üretilecek Ürün"
    )

    # Reçetenin versiyonu (Örn: v1.0, v1.1).
    version = models.CharField(max_length=10, default="1.0", verbose_name="Versiyon")
    # Şu an bu reçete mi kullanılıyor?
    is_active = models.BooleanField(default=True, verbose_name="Aktif Reçete mi?")
    description = models.TextField(blank=True, verbose_name="Üretim Notları")

    def __str__(self):
        return f"BOM: {self.parent_product.name} (v{self.version})"

# Ürün Ağacı Kalemi Oluşturma
class BOMItem(models.Model):
    # ForeignKey: Bir ürün ağacı başlığının altında birçok farklı malzeme olabilir.
    # "items": Bir reçete nesnesinin içindeki tüm malzemeleri sadece my_bom.items.all() bulunabilir.
    bom = models.ForeignKey(BOM, on_delete=models.CASCADE, related_name="items", verbose_name="Ürün Ağacı")
    # Child product: Ana ürünün (parent) oluşması için gereken alt parça.
    # on_delete=models.PROTECT: Bir malzeme bir reçetenin içinde kayıtlıysa, o malzemenin sistemden yanlışlıkla silinmesini engeller.
    child_product = models.ForeignKey(Product, on_delete=models.PROTECT, verbose_name="Bileşen")
    # Quantity: Malzemenin miktarı.
    quantity = models.DecimalField(max_digits=20, decimal_places=5, verbose_name="Miktar")
    # Fire Oranı (%): Üretim sırasında kaybolan/bozulan parça oranı.
    # Toplam İhtiyaç = Gerekli Miktar / (1 - Scrap Factor) formülü için kullanılır.
    scrap_factor = models.DecimalField(max_digits=5, decimal_places=2, default=0, verbose_name="Fire Oranı (%)")

    # Property: Bir fonksiyon gibi değil, sanki veritabanında kayıtlı bir alan gibi tanımlanması için.
    # Böylece kodun herhangi bir yerinde parantez kullanmadan item.total_required_quantity denilebilir.
    @property
    def total_required_quantity(self):
        """
        Toplam İhtiyaç = Gerekli Miktar / (1 - (Fire Oranı / 100))
        Bu fonksiyon, üretimdeki fireyi hesaba katarak gerçek hammadde ihtiyacını hesaplar.
        """
        # Eğer fire oranı 0 ise direkt miktarı döndür.
        if self.scrap_factor == 0:
            return self.quantity

        # Formülü uygula: quantity / (1 - (scrap_factor/100))
        multiplier = Decimal('1') - (self.scrap_factor / Decimal('100'))
        return self.quantity / multiplier

    def __str__(self):
        return f"{self.child_product.name} ({self.quantity})"

# Üretimin fiziksel olarak gerçekleştiği yer (Makine, Tezgah, Hat vb.).
class WorkCenter(models.Model):
    # Üretim merkezinin benzersiz kodu (Örn: CNC-01).
    code = models.CharField(max_length=20, unique=True, verbose_name="Üretim Merkezi Kodu")
    # Üretim merkezinin adı (Örn: Torna Tezgahı).
    name = models.CharField(max_length=100, verbose_name="Üretim Merkezi Adı")
    # Günlük çalışma saati: Kapasite planlama için kullanılır.
    daily_capacity_hours = models.DecimalField(max_digits=5, decimal_places=2, default=8.0, verbose_name="Günlük Kapasite (Saat)")
    hourly_rate = models.DecimalField( max_digits=10, decimal_places=2, default=100.0, verbose_name="Saatlik Maliyet (TL/Saat)")

    # Otonom Verimlilik Hesabı
    # Property: Kullanıcının girmesine gerek kalmadan, sistemdeki geçmiş kayıtlara bakarak verimliliği hesaplar.
    @property
    def efficiency_factor(self):
        """
        Verimlilik = Toplam Planlanan Süre / Toplam Gerçekleşen Süre
        Bu fonksiyon, bu makinede yapılan son 100 üretimin verilerini analiz eder.
        """
        # Makineye ait geçmiş üretim kayıtları çekilir.
        logs = self.production_logs.all().order_by('-id')[:100]  # Son 100 kayıt

        if not logs:
            return Decimal('0.80')  # Hiç veri yoksa varsayılan olarak %80 kabul et.

        total_planned = sum(log.planned_duration for log in logs)
        total_actual = sum(log.actual_duration for log in logs)

        if total_actual == 0:
            return Decimal('1.00')

        # Verimlilik oranının hesaplanması
        efficiency = total_planned / total_actual
        return min(efficiency, Decimal('1.20'))  # Maksimum %120 ile sınırlanır.

    def __str__(self):
        return f"{self.name} (Verimlilik: %{self.efficiency_factor * 100:.1f})"

    # Verimlilik Faktörü: Makinenin ne kadar efektif çalıştığını gösterir.
    efficiency_factor = models.DecimalField(max_digits=3, decimal_places=2, default=0.90, verbose_name="Verimlilik Faktörü")

    def __str__(self):
        return f"{self.name} (Verimlilik: %{self.efficiency_factor * 100:.1f})"

# Operasyon Aşaması: Ürünün hangi aşamalardan geçeceğini tanımlar.
class Operation(models.Model):
    # Operasyonun bağlı olduğu ana reçete.
    bom = models.ForeignKey(BOM, on_delete=models.CASCADE, related_name="operations", verbose_name="İlgili Reçete")
    # Bu işlemin hangi makinede yapılacağı.
    work_center = models.ForeignKey(WorkCenter, on_delete=models.PROTECT, verbose_name="Üretim Merkezi")
    # İşlem sırası:Üretim sırasını belirler.
    step_number = models.PositiveIntegerField(verbose_name="İşlem Sırası")
    # Yapılacak işin açıklaması
    description = models.CharField(max_length=255, verbose_name="İşlem Açıklaması")
    # Hazırlık Süresi (Dakika): Makineyi işe hazırlamak için gereken sabit süre.
    setup_time = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Hazırlık Süresi (Dakika)")
    # İşlem Süresi (Dakika/Adet): Bir adet ürünün makinede kalma süresi.
    cycle_time = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="İşlem Süresi (Dakika/Adet)")

    # Otonom Çevrim (İşlem) Süresi Hesabı
    # Property: Geçmiş üretim kayıtlarına bakarak birim başına düşen gerçek süreyi hesaplar.
    @property
    def actual_cycle_time(self):
        """
        Gerçekleşen Çevrim Süresi = (Toplam Harcanan Süre - Toplam Hazırlık) / Toplam Üretilen Miktar
        Bu fonksiyon, sahadaki gerçek süreyi hesaplar.
        """
        # Bir operasyona ait son 50 kayıt çekilir.
        logs = self.logs.all().order_by('-id')[:50]

        if not logs:
            return self.cycle_time  # Veri yoksa standart süreyi döndürür.
        total_actual_time = sum(log.actual_duration for log in logs)
        total_quantity = sum(log.quantity_produced for log in logs)
        # Her kayıt için bir hazırlık süresi düştüğümüzü varsayıyoruz.
        # Eğer operatör makineyi sabah açtı ve 100 adet üretip kaydı kapattıysa; 1 adet ProductionLog demektir.
        # Eğer operatör 100 adetlik işi 3 farklı güne bölüp 3 ayrı kayıt (log) attıysa; 3 kez hazırlık süresi.
        # logs.count() ifadesi "Kaç kez hazırlık/kurulum yapıldı?" sorusunun cevabıdır.
        total_setup_overhead = logs.count() * self.setup_time

        if total_quantity > 0:
            # Formül: Net Üretim Süresi / Toplam Miktar
            return (total_actual_time - total_setup_overhead) / total_quantity

        return self.cycle_time

    class Meta:
        # Operasyonları işlem sırasına göre otomatik dizer.
        ordering = ['step_number']
        verbose_name = "Operasyon"
        verbose_name_plural = "Operasyonlar"

        def __str__(self):
            return f"{self.bom.parent_product.name} - Adım {self.step_number}: {self.description}"

# VARDİYA: Üretimin hangi zaman diliminde yapıldığını takip eder.
class Shift(models.Model):
    name = models.CharField(max_length=50, verbose_name="Vardiya Adı") # Örn: Sabah, Akşam, Gece
    start_time = models.TimeField(verbose_name="Başlangıç Saati")
    end_time = models.TimeField(verbose_name="Bitiş Saati")

    def __str__(self):
        return self.name
# Personel: Üretim sahasında çalışan operatörler.
class Employee(models.Model):
    first_name = models.CharField(max_length=50, verbose_name="Adı")
    last_name = models.CharField(max_length=50, verbose_name="Soyadı")
    employee_id = models.CharField(max_length=20, unique=True, verbose_name="Sicil No")
    # Operatörün uzmanlık alanı (Örn: Kaynakçı, Montajcı). - Yeni
    skill_set = models.CharField(max_length=100, blank=True, verbose_name="Uzmanlık Alanı")

    def __str__(self):
        return f"{self.first_name} {self.last_name}"

# DEPO: Ürünlerin fiziksel olarak nerede tutulduğunu belirler.
class Warehouse(models.Model):
    name = models.CharField(max_length=100, verbose_name="Depo Adı")
    # Depo tipi (Örn: Hammadde, Yarı Mamul, Hurdalık).
    warehouse_type = models.CharField(max_length=20, choices=[
        ('RAW', 'Hammadde Deposu'),
        ('WIP', 'Ara Stok (İşlem Sırası)'),
        ('FINAL', 'Mamul Deposu'),
        ('SCRAP', 'Hurda Deposu'),
    ], verbose_name="Depo Tipi")

    def __str__(self):
        return self.name

# Üretim Kaydı: Makinelerin performansını ölçmek için gerçekleşen üretimlerin loglandığı yer.
class ProductionLog(models.Model):
    # Hangi makinede üretim yapıldı?
    work_center = models.ForeignKey(WorkCenter, on_delete=models.CASCADE, related_name="production_logs", verbose_name="Üretim Merkezi")
    # Hangi operasyon yapıldı?
    operation = models.ForeignKey(Operation, on_delete=models.SET_NULL, null=True, verbose_name="Yapılan Operasyon")
    # Planlanan Süre: Operasyon kartındaki süre (Beklenen).
    planned_duration = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Planlanan Süre (Dakika)")
    # Gerçekleşen Süre: Operatörün işi bitirdiği gerçek süre.
    actual_duration = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Gerçekleşen Süre (Dakika)")
    # Üretim tarihi.
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Kayıt Tarihi")
    # Üretilen miktar.
    quantity_produced = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Üretilen Miktar")

    # Üretim Sırasındaki Fire Hesabı
    # Reçetedeki tahminle (scrap_factor) kıyaslamak için.
    scrap_quantity = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Hurda Miktarı")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Kayıt Tarihi")

    def __str__(self):
        return f"{self.work_center.name} Kaydı - {self.created_at}"

# Üretim Emri: Üretimin planlandığı ve takip edildiği ana modül.
class ProductionOrder(models.Model):
    # Üretim durumlarını tanımlıyoruz.
    STATUS_CHOICES = [
        ('DRAFT', 'Taslak'),
        ('PLANNED', 'Planlandı'),
        ('IN_PROGRESS', 'Üretimde'),
        ('COMPLETED', 'Tamamlandı'),
        ('CANCELLED', 'İptal Edildi'),
    ]

    # Hangi ürünü üreteceğiz? (Sadece Mamul veya Yarı Mamul)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, verbose_name="Üretilecek Ürün", limit_choices_to={'product_type__in': ['SEMI', 'FINAL']})
    # Kaç adet üretilmesi planlanıyor?
    planned_quantity = models.DecimalField(max_digits=12, decimal_places=4, verbose_name="Planlanan Miktar")
    # Gerçekte kaç adet üretildi? (Kalite kontrol sonrası net miktar)
    actual_quantity = models.DecimalField(max_digits=12, decimal_places=4, default=0, verbose_name="Gerçekleşen Miktar")
    # Planlanan başlangıç ve bitiş tarihleri.
    start_date = models.DateField(verbose_name="Planlanan Başlangıç")
    due_date = models.DateField(verbose_name="Teslim Tarihi (Deadline)")
    # Üretimin şu anki durumu.
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DRAFT', verbose_name="Durum")

    # Property: Gecikme olup olmadığını kontrol eder.
    @property
    def is_delayed(self):
        from datetime import date
        if self.status != 'COMPLETED' and date.today() > self.due_date:
            return True
        return False

    # Otonom İlerleme ve Maliyet
    @property
    def current_progress(self):
        # Loglardan gelen gerçekleşen miktara göre ilerleme yüzdesini hesaplar.
        # self.logs.all(): Bu üretim emrine bağlı olan tüm ProductionLog (üretim kayıtlarını) getirir.
        # log.quantity_produced for log in ...: Her bir kaydın içine girer ve "Bu kayıtta kaç adet üretilmiş?" diye bakar.
        # sum(...): Operatörlerin farklı zamanlarda girdiği tüm miktarları toplar.
        actual = sum(log.quantity_produced for log in self.logs.all())
        # 0'a bölmesini engeller:
        if self.planned_quantity > 0:
            # actual değişkeni, o ana kadar üretilmiş toplam sağlam ürün miktarını verir.
            return round((actual / self.planned_quantity) * 100, 2)
            # return round((actual / self.planned_quantity) * 100, 2) (KPI Hesabı)
        return 0

    # DİNAMİK MALİYET HESABI
    @property
    def estimated_total_cost(self):
        """
        Her operasyonun süresini, o operasyonun yapıldığı makinenin saatlik ücretiyle çarpar.
        """
        # 1. Malzeme Maliyeti (BOM'dan fireli hesaplama ile gelir)
        mat_cost = sum(i.total_required_quantity * i.child_product.price for i in self.product.bom_header.items.all())

        # 2. İşçilik ve Makine Maliyeti
        labor_cost = Decimal('0')
        # hasattr: Eğer bu ürünün bir reçetesi varsa hesapla yoksa hata verme.
        # her ürünün reçetesi olmayabilir, bu yüzden hasattr kullanılır. Reçetesi yoksa hata vermez, diğerine geçer.
        if hasattr(self.product, 'bom_header'):
            for op in self.product.bom_header.operations.all():
                # Operasyon Süresi (Hazırlık + İşlem)
                op_duration_minutes = op.setup_time + (op.cycle_time * self.planned_quantity)

                # Dakikayı saate çevirip o makinenin (WorkCenter) saatlik ücretiyle çarpıyoruz.
                op_cost = (op_duration_minutes / Decimal('60')) * op.work_center.hourly_rate
                labor_cost += op_cost

        # Toplam Maliyet: (Malzeme * Miktar) + Operasyonların Toplam Maliyeti
        return (mat_cost * self.planned_quantity) + labor_cost

    def __str__(self):
        return f"İş Emri #{self.id} - %{self.current_progress}"

    class Meta:
        verbose_name = "Üretim Emri"
        verbose_name_plural = "Üretim Emirleri"

# Üretim Kaydı (Loglar)
class ProductionLog(models.Model):
    # Loglar artık bir Üretim Emrine bağlı olmalı.
    production_order = models.ForeignKey(ProductionOrder, on_delete=models.CASCADE, related_name="logs", verbose_name="Üretim Emri", null=True)
    work_center = models.ForeignKey(WorkCenter, on_delete=models.CASCADE, related_name="production_logs", verbose_name="Üretim Merkezi")
    operation = models.ForeignKey(Operation, on_delete=models.SET_NULL, null=True, related_name="logs", verbose_name="Yapılan Operasyon")
    planned_duration = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Planlanan Süre (Dakika)")
    actual_duration = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Gerçekleşen Süre (Dakika)")
    quantity_produced = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Üretilen Miktar")
    shift = models.ForeignKey(Shift, on_delete=models.SET_NULL, null=True, verbose_name="Vardiya")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Kayıt Tarihi")
    operator = models.ForeignKey(Employee, on_delete=models.SET_NULL, null=True, verbose_name="Operatör")

    def __str__(self):
        return f"{self.work_center.name} - {self.created_at}"


# Stok Hareketi: Stoktaki her türlü artış ve azalışın tarihçesini tutar.
class StockTransaction(models.Model):
    TRANSACTION_TYPES = [
        ('IN', 'Giriş (Satın Alma/Üretim)'),
        ('OUT', 'Çıkış (Satış/Sarf)'),
        ('SCRAP', 'Hurda Ayırımı'),
        ('ADJ', 'Sayım Farkı (Düzeltme)'),
    ]

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="transactions", verbose_name="Ürün")
    # Ne kadar değişti?
    quantity = models.DecimalField(max_digits=12, decimal_places=4, verbose_name="Değişim Miktarı")
    transaction_type = models.CharField(max_length=10, choices=TRANSACTION_TYPES, verbose_name="İşlem Tipi")
    # Hareketin hangi depoda gerçekleştiği.
    warehouse = models.ForeignKey(Warehouse, on_delete=models.CASCADE, verbose_name="Depo", null=True)
    # Bu hareket hangi iş emri veya satın alma ile ilgili?
    notes = models.CharField(max_length=255, blank=True, verbose_name="Notlar")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="İşlem Tarihi")

    # *args (sıralı) ve **kwargs (isimli) argümanları; Django'nun orijinal kaydet metodudur.
    # gelebilecek ekstra parametreleri (örn: güncelleme) güvenli ve kaybetmeden aktarmak için kullanılan esnek taşıma sağlar.
    def save(self, *args, **kwargs):
        # Her hareket oluşturulduğunda ana stok miktarını otomatik güncelle!
        # Bu işlem stok takibini otonom hale getirir.
        if self.transaction_type in ['OUT', 'SCRAP']:
            self.product.stock_quantity -= abs(self.quantity)
        else:
            self.product.stock_quantity += abs(self.quantity)

        self.product.save()
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = "Stok Hareketi"
        verbose_name_plural = "Stok Hareketleri"


# KALİTE KONTROL: Üretilen ürünlerin standartlara uygunluğunu denetler.
class QualityCheck(models.Model):
    # Hangi üretim emrinden gelen ürünler kontrol ediliyor?
    production_order = models.ForeignKey(ProductionOrder, on_delete=models.CASCADE, related_name="quality_checks", verbose_name="Üretim Emri")
    # Kontrol edilen miktar.
    checked_quantity = models.DecimalField(max_digits=12, decimal_places=4, verbose_name="Kontrol Edilen Miktar")
    # Onaylanan (Sağlam) miktar.
    approved_quantity = models.DecimalField(max_digits=12, decimal_places=4, verbose_name="Onaylanan Miktar")
    # Reddedilen (Hatalı) miktar.
    rejected_quantity = models.DecimalField(max_digits=12, decimal_places=4, verbose_name="Reddedilen Miktar")
    # Neden reddedildi? (Pareto analizi için önemlidir.)
    rejection_reason = models.TextField(blank=True, null=True, verbose_name="Red Nedeni")

    # Otonom Kalite Skoru Hesabı
    @property
    def quality_score(self):
        """Bu partinin başarı oranını yüzde olarak döner."""
        if self.checked_quantity > 0:
            return (self.approved_quantity / self.checked_quantity) * 100
        return 0

    def __str__(self):
        return f"Kalite Kontrol #{self.id} - Skor: %{self.quality_score:.1f}"

# MAKİNE BAKIM: Makinelerin arıza ve bakım kayıtlarını tutar.
class Maintenance(models.Model):
    MAINTENANCE_TYPES = [
        ('PREV', 'Periyodik Bakım'),
        ('REPAIR', 'Arıza Onarımı'),
        ('UPGRADE', 'İyileştirme (Kaizen)'),
    ]

    work_center = models.ForeignKey(WorkCenter, on_delete=models.CASCADE, related_name="maintenances", verbose_name="Üretim Merkezi")
    maintenance_type = models.CharField(max_length=10, choices=MAINTENANCE_TYPES, verbose_name="Bakım Tipi")
    # Makinenin duruş süresi (Kapasite hesabından düşmek için).
    downtime_minutes = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Duruş Süresi (Dakika)")
    description = models.TextField(verbose_name="Yapılan İşlem")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Bakım Tarihi")

    def __str__(self):
        return f"{self.work_center.name} - {self.get_maintenance_type_display()}"


# Müşteri: Ürünlerimizi satan aldığımız kurumlar veya kişiler.
class Customer(models.Model):
    name = models.CharField(max_length=255, verbose_name="Müşteri/Firma Adı")
    tax_number = models.CharField(max_length=20, blank=True, verbose_name="Vergi No")
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True, verbose_name="Adres")

    def __str__(self):
        return self.name


# SİPARİŞ - ÜRETİM TALEBİ
class SalesOrder(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name="orders", verbose_name="Müşteri")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, verbose_name="Sipariş Edilen Ürün", limit_choices_to={'product_type': 'FINAL'})
    quantity = models.DecimalField(max_digits=12, decimal_places=4, verbose_name="Sipariş Miktarı")
    order_date = models.DateField(auto_now_add=True, verbose_name="Sipariş Tarihi")
    delivery_date = models.DateField(verbose_name="Söz Verilen Teslim Tarihi")

    # Sipariş durum takibi
    is_shipped = models.BooleanField(default=False, verbose_name="Sevk Edildi mi?")
    def __str__(self):
        return f"Sipariş #{self.id} - {self.customer.name}"

# --- YENİ EKLENDİ (Arıza ve Bakım Analizi İçin) ---
class MaintenanceReason(models.Model):
    code = models.CharField(max_length=10, unique=True, verbose_name="Hata Kodu")
    description = models.CharField(max_length=255, verbose_name="Hata Açıklaması")
    category = models.CharField(max_length=20, choices=[
        ('MECHANICAL', 'Mekanik'),
        ('ELECTRICAL', 'Elektriksel'),
        ('OPERATOR', 'Operatör Kaynaklı'),
        ('EXTERNAL', 'Dış Kaynaklı'),
    ], verbose_name="Hata Kategorisi")

    def __str__(self):
        return f"[{self.code}] {self.description}"


# ARIZA BAKIM VE ANALİZİ
class Maintenance(models.Model):
    MAINTENANCE_TYPES = [
        ('PREV', 'Periyodik Bakım'),
        ('REPAIR', 'Arıza Onarımı'),
        ('UPGRADE', 'İyileştirme (Kaizen)'),
    ]
    work_center = models.ForeignKey(WorkCenter, on_delete=models.CASCADE, related_name="maintenances", verbose_name="Üretim Merkezi")
    reason = models.ForeignKey(MaintenanceReason, on_delete=models.SET_NULL, null=True, verbose_name="Arıza Nedeni")
    maintenance_type = models.CharField(max_length=10, choices=MAINTENANCE_TYPES, verbose_name="Bakım Tipi")
    downtime_minutes = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Duruş Süresi (Dakika)")
    description = models.TextField(verbose_name="Yapılan İşlem")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Bakım Tarihi")

# Kalite Kontrol Detayları İçin
class QualityParameter(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="quality_parameters")
    name = models.CharField(max_length=100, verbose_name="Parametre Adı")
    min_value = models.DecimalField(max_digits=10, decimal_places=4, verbose_name="Min. Değer")
    max_value = models.DecimalField(max_digits=10, decimal_places=4, verbose_name="Max. Değer")

class QualityMeasurement(models.Model):
    quality_check = models.ForeignKey(QualityCheck, on_delete=models.CASCADE, related_name="measurements")
    parameter = models.ForeignKey(QualityParameter, on_delete=models.CASCADE)
    measured_value = models.DecimalField(max_digits=10, decimal_places=4, verbose_name="Ölçülen Değer")



