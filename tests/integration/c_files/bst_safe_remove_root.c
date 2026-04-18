struct Node {
    int value;
    struct Node *left;
    struct Node *right;
};

void bst_safe_remove_root(struct Node* root) {
    struct Node *xl;
    struct Node *xr;
    struct Node *rl;
    struct Node *rr;
    struct Node *par;
    struct Node *par_par;
    if(root) { //1
        xl = root->left; //2
        xr = root->right;
        if(!xl) {
            free(root); //5
            if(xr) { //6
                root = xr;
            }
        }
        if (xl) {
            if(!xr) { //9
                free(root); //10
                root = xl;
            }
            else {
                rl = xr->left; //12
                par = xr;
                par_par = root;
                while(rl) { //15
                    par_par = par;
                    par = rl;
                    rl = rl->left;
                }
                rr = par->right; //19
                par->left = xl;
                if(par_par == root) { //21
                    free(root); //22
                    root = par;
                }
                else {
                    par_par->left = rr; //24
                    par->right = xr;
                    free(root);
                }
            }
        }
    }
} //27
