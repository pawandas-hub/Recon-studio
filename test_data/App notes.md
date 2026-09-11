













1. ekhon ja  ja format cholche sales er jonno sob formate sales hole credit note o thake abong tai ami age theke already extract file e excutive sheet e cn bole ekta option diyechi. tai je bu er je je cn thakbe tar tar total amount ar diffarencr okhane bosate hobe 
2. formate 1 er jonno db cn detar order_id main jar sqathe tomake sap ledger er ref.2 theke i'd match korte hobe. Tarpor tomake db cn id er against e date nite hobe jeta tumi created_at column e thakbe ar sathe sap ledger er ref.2 id er against e posting date niye match korte hobe. tarpor tomake db cn id er against e amount (Credit_note_amount jeta without gst amount(gst_percentage)hobe) nite hobe ar sap ledger e ref. 2 id er against e C/D (LC) theke total amount niye match korte hobe 
3. formate 2 er jonno db cn detar CN_ID main jar sqathe tomake sap ledger er ref.2 theke i'd match korte hobe. Tarpor tomake db cn id er against e date nite hobe jeta tumi CN_Date column e thakbe ar sathe sap ledger er ref.2 id er against e posting date niye match korte hobe. tarpor tomake db cn id er against e amount (Credit_note_amount hobe) nite hobe ar sap ledger e ref. 2 id er against e C/D (LC) theke total amount niye match korte hobe 
4. sob formate e recon korar somoy jodi kono emon data jeta sap ledger e sei formate er same BU against e ache kintu same formate er db data te nei tahole tar khetre sei line item gulo copy kore ekta notun sheet e past kore debe ar sheet name thakbe data not available in DB
5. arek ta notun recon style add hobe jeta formate 4 er under e hobe, jekhane db data theke so_id niye sap ledger er ref.1 ba ref.2 theke same id match korte hobe. tarpor db data theke so_id er against e DocDate er sathe sap ledger er ref.1 ba ref.2 er against e posting date niye match korte hobe. tarpor db data theke so_id er against e TaxableAmount er sathe sap ledger e ref.1 ba ref.2 er against e C/D (LC) er theke total amount niye match korte hobe. tarpor db data theke so_id er against e SAP_ID er sathe sap ledger er ref.1 ba ref.2 er against e Offset Account niye match korte hobe.
6. formate 4 er jonno db cn detar Credit_Note_ID main jar sqathe tomake sap ledger er ref.2 theke i'd match korte hobe. Tarpor tomake db cn id er against e date nite hobe jeta tumi Date column e thakbe ar sathe sap ledger er ref.2 id er against e posting date niye match korte hobe. tarpor tomake db cn id er against e Amount nite hobe ar sap ledger e ref. 2 id er against e C/D (LC) theke total amount niye match korte hobe

*ei sob kichu korte giye dekhbe jeno puro kono kichu change na hoye jay. ar ekhon jaja notun ready korbe ta jeno thik thak hoy keno na ami jokhon online link e push korar button click korbo tokhon jeno sob thik thak vabe complete hoy*




1. amar ei recon system e aro kichu notun dhoroner sale and collection data add korbo jar sheet e column name alada alada hobe 
2. ei notun dhoroner recon er jonno DB te tomar jonno InvoiceId column ta main thakbe are sap ledger er khetre ref.2 theke AFC chara invoice id nite hobe 
3. tarpor tomake db er invoice er sathe GRNID column ar sap ledger er Ref. 2 invoice er sathe Ref. 1 column er GRN id match korte hobe 
4. tarpor tomake db invoice er against e total sales amount (sales-(Discounts+UPI_Discount+Wallet_Discount+packingcharges)) er sathe sap ledger er invoice id er against er sathe Deb./Cred. (LC) theke total amount niye match korte hobe 
5. Tarpor tomake Db invoice er against er sathe card code and sap invoice er against e Offset Acct er customer code match korte hobe 
6. Tarpor tomake Db invoice er against er sathe DocDate and sap invoice er against e Posting Date match korte hobe 
7.tapor tomake DB invoice id er against e Freight amount match korte hobe, jeta tumi sap ledger 4020101013 er modhe Ref. 2 invoice id er against e Deb./Cred. (LC) column theke total amount niye

*inportent- ei sob kichu add korte giye jeno purono kono recon niyom change na hoye jay*


1. amar main gui app e reports er niche ekta button chai jeta click na korle notun kichu implement korle seta update hobe na streamlit online recon link e jotokhon na porjonto ami oi button ta click na kori 



1. ei pic e auto , light ar dark mode er je option gulo a6e segulo kJ korche na
2. tarpor total record, matched ar exceptions er je pic gulo te after recon er pore click korele je topup view dekhanor kotha normal app er moton seta dekhache na
3. tarpor dandiker opore konay ninjacarft er je logo ta ache seta aro tin size boro dekhay ar tar niche auto, light ar dark mode er option gulo ase 










1. amra je project ta toiri korechi seta khetre ekta link create koro streamlit ke sathe niye 
2. link ta emon hobe je ami sudhu ei link ta copy kore user ke debo se sei link ta google ba je kono browser e past kore run korle seta jeno run hoy 
3. ekhon ami amar project e ja ja recon korte parchi seta jeno sei user korte pare ar sei somoy amar ei laptop ta open rakha jeno mandetari na hoy. example dhoro ami amar ei link ta amar ekta bondhu ke dilam ar se sei link ta tokhon open na  kore ektu bade open korlo ar sei somoy amar laptop bondho ache, kinu sei bondhu ta nijer recon er jonno file upload korlo ar seta recon hoyeo gelo
4. ar poroborti somoye dhoro ami kichu update korchi amar main data te tokno amar jonno ekta button rakho pulished bole. jeta sudhu ami dekhte pabo amar app kintu kono sharable user dekhte na pay. ar ei button click korle tar pore jeno user er link update hoy autometic






1. ekhane layout e dashboard option e jodi click kori tahole tar modhey kokhon kon date e kon timke e sales recon ba collecgtion recon hoyechilo tar puro histry dekhabe last 30 line. ar ekhane kotogulo data te kaj hoyeche tar modhey koto match hoyeche ar koto faild hoyeche tar hisab dekhabe.
2. reconciletion er modhe ja ache tai dekhabe but protita image ar protita word clearcy visiable hote hobe 
3. data source option e kokhon , kothatheke ki data uload korchi kon file theke tar histry show hobe max last 10 line item 
4. exceptions item ta bad jabe 
5. reports e sob somoy current recon er recon details data show hote hobe 
6. period option er sathe je date lekha ache sekhane puro jaygate current long date and long time 12 hrs e dekhate hobe (kolkata, chennai, mumbai time zone hisabe)
7. tolarence +- 100 er bodole tolarence +- 1 dekhabe 
8. oporer search bar delete korte hobe 
9. total records option e jekhane pic ta ache sekahne single click korle ekta temporarly templete show hobe ar sekhne current total recon details data show hote hobe 
10. Match option e jekhane pic ta ache sekahne single click korle ekta temporarly templete show hobe ar sekhne current recon er reco details data theke sudhu match line item gulo show hote hobe
11. exceptions option e jekhane pic ta ache sekahne single click korle ekta temporarly templete show hobe ar sekhne current recon er reco details data theke sudhu not match line item gulo show hote hobe
12. ar puro layout er jekono jayga theke jekono word ba line jeno copy kora jay
* ar ei gulo korte giye jeno purono kono old flow nosto hoye jeno na jay 



















1. Sales Reconciliation Summary te je kono bu number boste pare, prothome check korbe je sap jokhon match korcho tokhon sap te invoice id/ref id er sathe kon Business Unit  ache same row te. tarpor sei moto table e sei bu bosabe ar Total line item, as per DB,	DB Amount,	SAP Amount & Amount Variance jothariti sob number bosbe calculation kore. ei khetre je kono sales data r sate je kono sales ledger hote pare. ar ha ei ta sudhu sales recon er somoy use hobe and collection er jonno alada hobe seta porer point e bolchi
2. collection er jonno Particulars	BU	Total line item as per DB	DB Amount	SAP Amount	Amount Variance
Sales	24	0	0	0	0
Sales	14	0	0	0	0
CN	24	0	0	0	0
CN	14	0	0	0	0
ei same table use hobe but Particulars er column e bank name hobe, tarpor bu column e bu headline er jaygay Acount number hobe tarpor total line item as per db te sei perticuler bank account statement e kotogulo total creadit line ache seta bosbe. tarpor db amount e oi perticuler account number er creadit amount ache setar total bosbe. tarpor ar sap amount sei perticuler account er gl er total Credit (LC) r amount bosbe. ar tarpor normal Variance calculation hoye number ta bosbe 
3. collection reconcile er somoy sheet name sales - SAP Data er jaygay collection - SAP Data hobe ar sheet name sales - DB Data er jaygay collection - Bank Data hobe. Mone rakhbe egulo kintu alada alada kore kaj korbe. sales er recon er jonno ja details diyechi tar sathe jeno collection recon er details guliye na jay 

4.er songe ekta jinish add korte hobe ar seta holo collection recon er somoy UTR er pasapasi Offset Account theke utr onujai details add hobe 

*ar ei somosto kaj korte giye jeno purono kono kaj nosto na hoye jay 






























export file e sales er jonno alada kore duto sheet add hobe jar ekta sheet e thakbe all sap data jeta ami upload korchi ar onno file e thakbe all db data jeta ami update korchi. ar er sathe excutive summary sheet e sales er jonno ekta table create hobe jekhane choyta column ar pach ta row thakbe example hisabe Particularse	BU	Total line item as per DB	DB Amount	SAP Amount 	Amount Variance
Sales	24				
Sales	14				
CN	    24				
CN	    14				
nite paro
















CMS collection recon er jonno prothome Account Number theke '107505004797 group nebe, tarpor  TransactionID theke recon er jonno id nebe ar SAP ledger theke Details er theke id niye recon hobe. tarpor same CMS id er sathe sap er ledger er id then CMS id amount (Deno Total column) er sathe sap ledger er id amount and last e CMS id ActionDate er sathe sap ledger er posting date check hobe. ar ei sob kichu korte purono ja ache ta jeno nosto na hoy
CMS te ActionDate holo bank date TransactionID holo bank utr, ar account number er jaygay CMS_CCA_Account lekha asbe 














paynearby collection recon er jonno prothome busines tyoe theke omni channel group nebe, tarpor Txn Status jodi success thake tobei PNBTransactionID theke recon er jonno id nebe ar SAP ledger theke Details er theke id niye recon hobe. tarpor same paynearby id er sathe sap er ledger er id then paynearby id amount er sathe sap ledger er id amount and last e paynearby id Txn Date er sathe sap ledger er posting date check hobe. ekhane ja changes hobe tai jeno baire je recon application er shortcut a6e tateo jeno update hoy. ar ei sob kichu korte purono ja ache ta jeno nosto na hoy
paynearby te Txn Date holo bank date PNBTransactionID holo bank utr jeta ei pic e dekhchi nite pareni ar account number er jaygay PNB_CCA_Account lekha asbe 


















1. Puro feature end to end ekbar dekho, ar from scratch theke UI banao, Karon ekhon kar UI khub e clunky. Ami chai tumi puro feature ta end to end dekhe scratch theke sundor minimalistic materialistic UI banao, jaate eta production ready sundor dekhte laage, ar lokjon o prosongsha kore. Mone rakhbe ete jeno existing feature breakage na hoy. Sobcheye boro kotha progress jeno dekhaye, seta boro file load er hok, batch kaaj e hok, export ei hok. Sob kichu jeno user level e ami dekhte pai je ami jodi kono time e long running task er jonno wait kori, seta jeno user level eo ami bujhte pari.
2. Amader ei kaaj e onek boro boro files load hoy, ar operation hoy, ami chai tumi python er full potential use koro, seta multi processing, multi threading, batching, pandas etc. Seta ami tomar upor chere dilam. Seta obossoi jaate existing functinoality breakage na hoy, abar bhalo kore modular structure thaake.
3. Tumi aage test data dekho. Ami apatoto Omni&farmer and sales segregated rekhechi jaate tomar bujhte subidha hoy, kintu diner seshe ami chai aro different jinis add korar in future. sekhane onno format er o data hote pare. ami jodi sales ar collection douto recon i eksathe korte chai thale ledger code 4020101001 & 4020101003 & 4020101022 etc, jabe sales recon er jonno ar bank er sob statement i jabe collection recon er jonno but sales er khetre ref-id/invoice-id jeta db source file e thakbe seta must follow hobe and collection er khtre jeta bank er utr hobe seta must follow hobe. ar ei sob kichu korte giye jeno amar purono kono kaj bondho hoye na jay 
4. in that outlate i want some changes

add i column where mention the recon belongs from sales or collection
each column showing the filter option and wher i can esyly put the words & numeric both
upper processing bar percentage is not showing

I need you to independantly think on the whole repository, because I was using a dumb model, so it's not listening to anything and maybe even structred wrong. Ask clarifying questions , ar ei feature ta tomake end to end sundor kore kore dite hobe









amar collection reconciletion korte hobe bank data and sap ledger er modhe jekhane bank utr holo main identification number 
er modhey duti type er bank statement thakbe ekta holo icici abong arfekta holo scb 
icici te amar transaction i'd ta holo main utr column 
abong scb te (=MID(C2,FIND("|",C2) + 1,FIND(" ",C2) - 1 - (FIND("|",C2))) & =MID(C2,FIND("/",C2) + 1,FIND(" ",C2) - 1 - (FIND("/",C2)))) use kore utr ber kore reconcile korte hobe 
jodi kono utr sap ledger e na pawoa jay tokhon sap details column e je exiting utr ache seta ekbar bank statement er description column e check kore tar against e je utr ache seta use korte hobe 
icici bank statement er transaction column er sathe sap er details column check hobe tarpor same utr er sathe both side amount check hobe (example icici bank er Deposit Amt (INR) against Tran. Id with total  C/D (LC) amount against Details utr)
jodi kono jaygay sap data te dekha jay je reverse kora ache tokhon sei row er Origin No. name er column er sathe match kore same number er je arekta roe paowa jabe tokhon sei roe er details column er utr niye reverse er jaygay bosiye recon korte hobe 
scb statement er sathe same jinish ta korte hobe 
ar jodi kono kichu vul jay sei khetre lal rong diye mention korte hobe 
protita vul line item er proper remarks dite hobe je je karone vul hoche 
over ui te 
