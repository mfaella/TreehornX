struct Node {
    int data;
    struct Node *left;
    struct Node *right;
};

void bst_remove_root_unsafe(struct Node **root) {
    struct Node *x;
    struct Node *ret;
    struct Node *xl;
    struct Node *xr;
    struct Node *rl;
    struct Node *rr;
    struct Node *par;
    struct Node *par_par;

    x = *root;
    if (x == 0) {
        ret = x;
    }
    else {
        xl = x->left;
        xr = x->right;
    
        if (xl == 0) {
            if (xr == 0) {
                free(x);
                ret = 0;
            } else {
                ret = xr;
                free(x);
            }
        } else {
            // Case: left child exists
            // (note: missing check for xr == NULL as per your comment)
            rl = xr->left;
            par = xr;
            par_par = x;
    
            while (rl != 0) {
                par_par = par;
                par = rl;
                rl = rl->left;
            }
    
            rr = par->right;
            par->left = xl;
    
            if (par_par == x) {
                free(x);
                ret = par;
            } else {
                par_par->left = rr;
                par->right = xr;
                free(x);
                ret = par;
            }
        }
    }
}
