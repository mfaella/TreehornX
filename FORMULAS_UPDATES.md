## Risoluzione dei loop all'interno di una catena di step interni
Il flag event può assumere anche il valore "Loop". Questo evento sta a indicare che è stato individuato un loop in una sequenza
di step interni. Andando a imporre il limite della lunghezza solo alla label compressa si consente una generazione infinita di label che
caratterizzano step locali che si ripetono.

## Risoluzione del problema delle collisioni su assegnamenti a campi puntatore
Il problema sorge quando in una catena di step interni viene inserito l'evento \<pfield:=q> (dove q non punta al nodo corrente) e in seguito viene aggiunto <q:=here>. Le formule originali applicate all'encoding della compressione interpretano che pfield punti al nodo corrente.
Per sopraggiungere a questo problema, aggiungiamo l' evento \<pfield:=here>, in questo modo è possibile determinare se è necessario ritrovare il puntatore a cui punta pfield, o so che il pfield punta al nodo corrente
Le formule che subiscono cambiamenti da questo aggiornamento dell'encoding sono step_assgn_to_field, is_pfield_nil, is_pfield_implicit, is_pfield_ptr e step_assgn_from_field

### step_assgn_to_field
step_assgn_to_field(σ,a,τ,b,p,q,pfield)=  
  find_or_fail(σ,a,τ,b,p)∨  
  (stop_rewind(σ,a,p)∧σ^a.next=(−,a+1)∧advance_pc(σ^a,τ^b)∧  
  +(points_here(σ,a,q)->τ^b.event=⟨pfield:=here⟩)∧  
  +(¬points_here(σ,a,q)->((¬σ^a.isnil_q∧τ^b.event=⟨pfield:=q⟩)∨(σ^a.isnil_q∧τ^b.event=⟨pfield:=nil⟩)))∧  
  -((¬σ^a.isnilq​∧τ^b.event=⟨pfield:=q⟩)∨(σ^a.isnilq​∧τ^b.event=⟨pfield:=nil⟩))∧  
  default_avail,active,val,d,isnil,active_child(σ^a,τ^b−1,τ^b)).

### is_pfield_nil
Sintatticamente non subisce cambiamenti ma ⟨pfield:=∗⟩ include anche ⟨pfield:=here⟩  
is_pfield_nil(σ,a,pfield)=  
i∈[2,a]⋁​​σ^i.event=⟨pfield:=nil⟩∧j∈[i+1,a]⋀​σ^j.event!=⟨pfield:=∗⟩​

### is_pfield_implicit
Sintatticamente non subisce cambiamenti ma ⟨pfield:=∗⟩ include anche ⟨pfield:=here⟩  
is_pfield_implicit(σ,a,pfield)=  
j∈[2,a]⋀σ^j.event!=⟨pfield:=∗⟩.

### is_pfield_ptr
Sintatticamente non subisce cambiamenti ma ⟨pfield:=∗⟩ include anche ⟨pfield:=here⟩, se al momento dell'assegnamento here punta al nodo corrente, sarebbe stato assegnato l'evento ⟨pfield:=here⟩  
is_pfield_ptr(σ,a,pfield,r,i)=  
σ^i.event=⟨pfield:=r⟩∧j∈[i+1,a]⋀σ^j.event!=⟨pfield:=∗⟩

### is_pfield_here
questo predicato è soddisfatto se il campo puntatore punta al node corrente  
is_pfield_here(σ,a,pfield)=  
i∈[2,a]⋁​​σ^i.event=⟨pfield:=here⟩∧j∈[i+1,a]⋀​σ^j.event!=⟨pfield:=∗⟩​

### step_assgn_from_field
step_assgn_from_field​(σ,a,τ,b,p,q,pfield)=

Case 1: q is nil; null pointer dereference  
(σ^a.isnil_q∧error(σ^a,τ^b))∨

Case 2a: phase I; q points elsewhere; start or keep rewinding  
(σ^a.event!=RWD(∗,∗)∧rewind(σ,a,τ,b,q))∨

Case 2b: phase II; r points elsewhere; start or keep rewinding  
(σ^a.event=RWD(i,r)∧rewind_special(σ,a,τ,b,r,i))∨

Case 3a: end of phase I; q points to the current node  
(σ^a.event!=RWD(∗,∗)∧stop_rewind(σ,a,q)∧  
((is_pfield_nil(σ,a,pfield)∨  
(is_pfield_implicit(σ,a,pfield)∧¬σ^a.active_childindex(pfield)))→  
step_assign_nil(σ^a,τ^b,p))∧  
((is_pfield_implicit(σ,a,pfield)∧σ^a.active_childindex(pfield))→  
(σ^a.next=(index(pfield),b)∧advance_pc(σ^a,τ^b)∧  
τ^b.event=⟨p:=here⟩∧  
default_avail,active,val,d,isnil,active_child​(σ^a,τ^b−1,τ^b)))∧  
+(is_pfield_here(σ,a,pfield)→  
-r∈PVP,i∈\[2,n]⋀((is_pfield_ptr(σ,a,pfield,r,i)∧points_here(σ,i,r))→  
set_ptr_here(σ^a,τ^b,p))∧  
+r∈PVP,i∈\[2,n]⋀is_pfield_ptr(σ,a,pfield,r,i)→  
-r∈PVP,i∈\[2,n]⋀((is_pfield_ptr(σ,a,pfield,r,i)∧¬points_here(σ,i,r))→  
rewind_special(σ,a,τ,b,r,i)))∨  

Case 3b: end of phase II; r points to the current node
(σ^a.event=RWDi,r∧points_here(σ,i,r)∧set_ptr_here(σ^a,τ^b,p)).

## Risoluzione di incorrettezza delle formule per mancato assegnamento di isnil in p := q->field
### step_assgn_from_field
step_assgn_from_field​(σ,a,τ,b,p,q,pfield)=

Case 1: q is nil; null pointer dereference  
(σ^a.isnil_q∧error(σ^a,τ^b))∨

Case 2a: phase I; q points elsewhere; start or keep rewinding  
(σ^a.event!=RWD(∗,∗)∧rewind(σ,a,τ,b,q))∨

Case 2b: phase II; r points elsewhere; start or keep rewinding  
(σ^a.event=RWD(i,r)∧rewind_special(σ,a,τ,b,r,i))∨

Case 3a: end of phase I; q points to the current node  
(σ^a.event!=RWD(∗,∗)∧stop_rewind(σ,a,q)∧  
((is_pfield_nil(σ,a,pfield)∨  
(is_pfield_implicit(σ,a,pfield)∧¬σ^a.active_childindex(pfield)))→  
step_assign_nil(σ^a,τ^b,p))∧  
((is_pfield_implicit(σ,a,pfield)∧σ^a.active_childindex(pfield))→  
(σ^a.next=(index(pfield),b)∧advance_pc(σ^a,τ^b)∧  
τ^b.event=⟨p:=here⟩∧  
+r∈PVP/{p}⋀τ^b.isnil_r=σ^a.isnil_r∧τ^b.isnil_p=false
default_avail,active,val,d,active_child​(σ^a,τ^b−1,τ^b)))∧  
+(is_pfield_here(σ,a,pfield)→  //correzione della sezione precedente
-r∈PVP,i∈\[2,n]⋀((is_pfield_ptr(σ,a,pfield,r,i)∧points_here(σ,i,r))→  //correzione della sezione precedente
set_ptr_here(σ^a,τ^b,p))∧  
+r∈PVP,i∈\[2,n]⋀is_pfield_ptr(σ,a,pfield,r,i)→  // correzione della sezione precedente
-r∈PVP,i∈\[2,n]⋀((is_pfield_ptr(σ,a,pfield,r,i)∧¬points_here(σ,i,r))→  //correzione della sezione precedente
rewind_special(σ,a,τ,b,r,i)))∨  

Case 3b: end of phase II; r points to the current node
(σ^a.event=RWDi,r∧points_here(σ,i,r)∧set_ptr_here(σ^a,τ^b,p)).
