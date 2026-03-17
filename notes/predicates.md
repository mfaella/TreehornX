# Perdicates list

## frame structure

![image info](./rsc/frame_struct.png)


## CHCs

![image-info](./rsc/labels.png)

## first_frame(sigma)
assert constraint of first frame of each label

![image info](./rsc/first_frame.png)


## initial(sigma)
enforce constraint on the first frame

![image info](./rsc/initial.png)


## start(sigma)
assert constraint for the two first frame of the root node label

![image info](./rsc/start.png)


## frame_exit(f)
represent the exit status of a frame

![image info](./rsc/frame_exit.png)


## label_exit(sigma)
represent the exit status of a label

![image info](./rsc/label_exit.png)


## consistent_child(tau, j, sigma)
assert that that is there a knitted tree where a node u labeled with tau is the jth child of a node v labeled with sigma
?in left hand operand of implication isn't implicit that or's operands are both true or both false?

![image info](./rsc/consistent_child.png)


## consistent_first_frames (tau,j,sigma)
enforce the constraint of the first frame of each node

![image info](./rsc/consistent_first_frame.png)


## psi_internal(sigma, f)
assert the step on the following frame on the same label

![image info](./rsc/psi_internal.png)


## psi_down(sigma, j, tau, f)
assert the step on the following frame going to one of the children

![image info](./rsc/psi_down.png)


## psi_up(sigma, j, tau, f)
assert the step on the following frame going to the parent

![image info](./rsc/psi_up.png)

?setting a p belongs PV to nil is not considered an update?


## continues(sigma^a)
assert that the ath frame is a used frame and is not a terminal

![image info](./rsc/continues.png)


## step(sigma, a; tau, b)
enforces the constraints for each instruction

![image info](./rsc/step.png)


## step_skip(f1, f2)

![image info](./rsc/step_skip.png)

## default(f_prev, f_below, f)
enforces constraint on default values, f_below is the previous frame of f in the label

![image info](./rsc/default.png)


## default_active_child(f_prev, f_below, f)

![image info](./rsc/default_active_child.png)


## step_assgn_nil(f1, f2, p)

![image info](./rsc/step_assgn_nil.png)


## advance_pc(f1, f2)

![image info](./rsc/advance_pc.png)


## step_assgn_exp(f1, f2, d, exp)

![image info](./rsc/step_assgn_exp.png)


## step_new(sigma a, tau b-1, tau b, p)

![image info](./rsc/step_new.png)


## step_local_branch

![image info](./rsc/step_local_branch.png)


## step_assgn_cond(sigma,a,tau,b,dbool,p,q)

![image info](./rsc/step_assgn_cond.png)

![image info](./rsc/step_assgn_cond_default.png)


## step_assgn_ptr(sigma,a,tau,b,p,q)

![image info](./rsc/step_assgn_ptr.png)


## set_ptr_here(f1, f2, here)

![image info](./rsc/set_ptr_here.png)


## step_assgn_to_field(sigma,a,tau,b,p,q,pfield)

![image info](./rsc/step_assgn_to_field.png)
step_assign_nil_to_field is a variant changing the event to p->pfield:=nil 


## step_assgn_to_data(sigma,a,tau,b,p,exp)

![image info](./rsc/step_assgn_to_data.png)


## step_assgn_to_var(sigma,a,tau,b,d,p)

![image info](./rsc/step_assgn_to_var.png)


## step_free(sigma,a,tau,b,d,p)

![image info](./rsc/step_free.png) 


## step_cmp_ptr(sigma, a, tau, b, p, q, neg)

![image info](./rsc/step_cmp_ptr.png) 


## find_or_fail(sigma,a,tau,b,p)

![image info](./rsc/find_or_fail.png)


## error(f1, f2)

![image info](./rsc/error.png)


## step_assgn_from_field(sigma,a,tau,b,p,q,pfield)

![image info](./rsc/step_assgn_from_field.png)


## is_pfield_nil(sigma, a, pfield)

![image info](./rsc/is_pfield_nil.png)


## is_pfield_ptr(sigma,a,pfield,r,i)

![image info](./rsc/is_pfield_ptr.png)


## is_pfield_implicit(sigma,a,pfield)

![image info](./rsc/is_pfield_implicit.png)


## rewind(sigma, a, tau, b, q)
RWD_b indicates that the next frame in the lace will rewind from sigma_b
controlla che l'ultimo update sia stato effettuato aggiungendo un nuovo nodo andando da tau verso sigma.
Nella forma ottimizzata last_visit può essere eliminata

![image info](./rsc/rewind.png)


## cur_rewind_pos(sigma, a)

![image info](./rsc/cur_rewind_pos.png)


## points_here(sigma, a, q)

![image info](./rsc/points_here.png)


## last_upd(sigma, a, q)

![image info](./rsc/last_upd.png)


## last_visit(tau, dir, j)

![image info](./rsc/last_visit.png)


## rewind2(sigma, a, tau, b, q1, q2)
completely removed the use of last_visit because in the algorothm is implicit
manca tau b.next = ?
![image info](./rsc/rewind2.png)


## rewind_special(sigma, a, tau, b, r, a')

![image info](./rsc/rewind_special.png)


## stop_rewind(sigma, a, q) and stop_rewind2(sigma, a, q1, q2)

![image info](./rsc/stop_rewind.png)


## are_equal_after_rewind(sigma, a, p, q)

![image info](./rsc/are_equal_after_rewind.png)











